"""
Market Pulse 입력 수집기 — Claude 없이 도는 Python 명령.

    python -m marketpulse.collector run [--date 2026-11-25] [--out DIR] [--only base,universe,basket,news]
                                        [--budget-min 25] [--no-wait] [--reference DIR] [--publish [가지]]
        오늘(KST) 입력을 받는다. 이미 받은 계열은 건너뛰고 빠진 것만 받는다(이어 받기).
        종료 코드 0 = 다 받음 · 75 = 일부 남음(다음 시도 시각을 출력한다 — 그 뒤에 같은 명령을 다시 부른다) · 73 = 이미 도는 중
    python -m marketpulse.collector status [--date D] [--out DIR]      받은 것 · 빠진 것 · 공급처별 성공률 · 회로 상태 · FULL/PARTIAL 판정
    python -m marketpulse.collector news [--date D] [--out DIR]        기사(RSS)만 한 번 더 받아 합친다(07:30 KST 뒤에 부른다)
    python -m marketpulse.collector inventory [--md 파일]              수집 대상 전체와 공급처 순서 목록
    python -m marketpulse.collector breaker [--reset 호스트]           공급처 회로 상태(쉬는 중인지 · 언제 풀리는지)
    python -m marketpulse.collector pull [--date D] [--branch 가지]     다른 곳에서 올린 수집 결과를 전달 가지에서 꺼낸다

기본 저장 위치는 marketpulse/data/inputs/<날짜>/ (환경변수 MARKETPULSE_INPUTS_DIR 로 바꾼다).
회로 상태는 .marketpulse_state/ (MARKETPULSE_STATE_DIR). 키는 환경변수로만 읽는다(FRED_API_KEY · TWELVEDATA_API_KEY) — 출력하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .engine import EXIT_OK, GROUPS, Collector, build_plans, inputs_root, kst_today, prune, state_dir


def _out(a) -> tuple[date, Path]:
    day = date.fromisoformat(a.date) if a.date else kst_today()
    return day, Path(a.out) if a.out else inputs_root() / day.isoformat()


def _print_status(c: Collector) -> None:
    st = c.status
    print(f"수집 폴더 {c.out} · {st.get('day')} · 마지막 갱신 {st.get('updated_at')} · 실행 {len(st.get('runs') or [])}회")
    for g in GROUPS:
        plan = c.plans[g]
        got = sum(1 for i in plan.instruments if c.have(g, i.id))
        rows = st["series"].get(g) or {}
        by = {}
        for i in plan.instruments:
            if not c.have(g, i.id):
                by.setdefault((rows.get(i.id) or {}).get("state") or "아직 시도 안 함", []).append(i.id)
        print(f"  {g:9s} 직접 수집 {got}/{len(plan.instruments)}" + (f" · 파생 {len(plan.derived)}개는 재료가 있으면 계산" if plan.derived else ""))
        for k, ids in by.items():
            print(f"    {k}: {', '.join(ids[:14])}{' …' if len(ids) > 14 else ''} ({len(ids)})")
    print("  공급처별 (성공 / 실패 / 회로로 건너뜀 / 키 · 파일 없음):")
    for name, r in sorted((st.get("providers") or {}).items()):
        tot = r.get("ok", 0) + r.get("failed", 0)
        rate = f"{r.get('ok', 0) / tot:.0%}" if tot else "—"
        print(f"    {name:11s} {r.get('ok', 0)} / {r.get('failed', 0)} / {r.get('circuit_skipped', 0)} / {r.get('unavailable', 0)} · 성공률 {rate}")
    for host, b in (c.breaker.snapshot() or {}).items():
        if b["state"] != "closed" or b.get("last_status"):
            print(f"  회로 {host}: {b['state']}" + (f" · {b['open_until']} 까지(남은 {b['retry_in_sec']}초)" if b["state"] == "open" else "") +
                  f" · 직전 응답 {b.get('last_status')} Retry-After={b.get('last_retry_after')} 본문={b.get('last_body')!r}")
    ins = st.get("input_status")
    if ins:
        print(f"  07:30 KST 기준 입력 상태: {json.dumps(ins['counts'], ensure_ascii=False)}")
        print(f"  판정 {ins['gate']['verdict']}" + (" — " + " · ".join(ins["gate"]["reasons"]) if ins["gate"]["reasons"] else ""))
    if st.get("next_retry_at"):
        print(f"  다음 시도 가능 시각: {st['next_retry_at']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="marketpulse.collector", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["run", "status", "news", "inventory", "breaker", "pull"])
    p.add_argument("--date"); p.add_argument("--out"); p.add_argument("--only", default="base,universe,basket,news")
    p.add_argument("--budget-min", type=float); p.add_argument("--no-wait", action="store_true")
    p.add_argument("--reference"); p.add_argument("--publish", nargs="?", const="collector-inputs")
    p.add_argument("--branch", default="collector-inputs"); p.add_argument("--remote", default="origin")
    p.add_argument("--md"); p.add_argument("--reset"); p.add_argument("--force", action="store_true")
    a = p.parse_args(argv)

    if a.cmd == "inventory":
        from .inventory import render
        text = render(build_plans())
        if a.md:
            Path(a.md).write_text(text, encoding="utf-8")
            print(f"{a.md} 에 썼다 ({len(text.splitlines())}줄)")
        else:
            print(text)
        return 0
    if a.cmd == "breaker":
        from ..adapters.breaker import ProviderBreaker
        from ..archive.input_status import load_collection_config
        path = state_dir() / "provider_breaker.json"
        b = ProviderBreaker(path, config=load_collection_config().get("breaker"))
        if a.reset:  # 사람이 '이제 풀렸다' 를 확인했을 때만 쓴다
            b._doc["hosts"].pop(a.reset, None)
            b._save()
            print(f"{a.reset} 회로 상태를 지웠다")
        print(json.dumps({"file": str(path), "hosts": b.snapshot(), "next_retry_at": b.next_retry_at()}, ensure_ascii=False, indent=1))
        return 0
    day, out = _out(a)
    if a.cmd == "pull":
        from .handoff import pull
        if (out / "series_base.json").is_file() and not a.force:  # 여기서 이미 받은 것을 넘겨받은 것으로 덮어쓰지 않는다
            print(f"{out} 에 이미 수집분이 있다 — 덮어쓰지 않는다(넘겨받은 것으로 바꾸려면 --force)")
            return 1
        got = pull(day.isoformat(), out, branch=a.branch, remote=a.remote)
        if got and (out / "checkpoint").is_dir():
            import shutil
            shutil.rmtree(out / "checkpoint")  # 넘겨받은 계열 파일에서 체크포인트를 다시 만든다
        print(f"{day} 수집 결과 {len(got)}개 파일을 {out} 에 꺼냈다: {', '.join(got)}" if got else f"전달 가지 {a.branch} 에 {day} 수집 결과가 없다")
        return 0 if got else 1
    c = Collector(day, out, reference=Path(a.reference) if a.reference else None)
    if a.cmd == "status":
        _print_status(c)
        return 0
    if a.cmd == "news":
        print(json.dumps(c.collect_news(), ensure_ascii=False))
        c._save_status()
        return 0
    only = [x.strip() for x in a.only.split(",") if x.strip()]
    code = c.run(groups=tuple(g for g in GROUPS if g in only), news="news" in only,
                 budget_sec=a.budget_min * 60 if a.budget_min is not None else None, wait=False if a.no_wait else None)
    _print_status(c)
    gone = prune(out.parent, int(c.run_cfg.get("keep_days", 4)), day) if not a.out else []
    if gone:
        print(f"오래된 수집 폴더를 지웠다: {', '.join(gone)}")
    if a.publish:
        from .handoff import publish
        commit = publish(out, day.isoformat(), branch=a.publish, remote=a.remote)
        print(f"전달 가지 {a.publish} 로 올렸다: {commit[:10]}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
