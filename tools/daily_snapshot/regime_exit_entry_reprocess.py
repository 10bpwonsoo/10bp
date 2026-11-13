"""공식 regime Exit / Entry(exit_entry_v2) 재정렬 — effective_from(2026-11-09) 이후 이미 저장된 Daily Snapshot 만, 날짜 오름차순으로.

    python tools/daily_snapshot/regime_exit_entry_reprocess.py 2026-11-09 2026-11-10 2026-11-11 2026-11-12          # 미리 보기(쓰지 않음)
    python tools/daily_snapshot/regime_exit_entry_reprocess.py 2026-11-09 ... --apply --reason "..." --by NAME        # 상태 로그 · 캡처 · 저장본 correction

각 날짜 S 는 S 저장본(그 cutoff 의 데이터: 선택 · 주식 판독 · 핵심 변수 · cross-asset z · 이벤트 · 뉴스)과 S 시점까지의 history 행만 쓴다 — 뒤 날짜를 보지 않는다.
바꾸는 것은 실시간 탭의 공식 regime 표시뿐이다: cockpit.history(공식 띠 · CURRENT · 전환) · market_now(공식 · 후보 · 이탈 · 진입 · 문장) ·
cross_asset(공식 regime 기준 대조, 저장된 z 그대로) · tone 의 regime 대조. 원천 데이터 · factor · 후보 선택은 그대로다.
저장본은 archive correct 경로로만 교체한다(이전 파일 superseded/ · meta.corrections). effective_from 이전 날짜는 받지 않는다.
"""
import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from marketpulse.ai import transition_read as TR  # noqa: E402
from marketpulse.archive.service import DailyArchiveService  # noqa: E402
from marketpulse.archive.store import ArchiveStore  # noqa: E402
from marketpulse.config.settings import get_settings  # noqa: E402
from marketpulse.engines import regime_select as RS  # noqa: E402
from marketpulse.engines import regime_state as RSM  # noqa: E402
from marketpulse.engines.cockpit import LABEL_TEXT, cross_asset_read, cross_asset_rows, cross_asset_texts, load_cockpit_config, now_history_fields, now_sentence  # noqa: E402
from marketpulse.engines.market_tone import build_market_tone  # noqa: E402
from marketpulse.engines.regime_history import build_regime_history  # noqa: E402
from marketpulse.history.assemble import market_history  # noqa: E402
from marketpulse.history.integrate import _lead_in, _window  # noqa: E402
from marketpulse.history.manager import DailySnapshotManager  # noqa: E402
from marketpulse.history.store import JsonDirStore  # noqa: E402
from marketpulse.models.snapshot import IntelligenceSnapshot  # noqa: E402

CAP = ROOT / "marketpulse" / "data" / "captures"


def _j(x):
    return json.loads(x.model_dump_json()) if hasattr(x, "model_dump_json") else x


def process(day: date, *, svc, mgr, log, cfg, apply: bool) -> dict:
    hcfg = cfg.get("history") or {}
    smcfg = RSM.sm_config(hcfg)
    eff = RSM.effective_from(smcfg)
    if eff is None or day < eff:
        raise SystemExit(f"{day} 는 {eff} 이전 — legacy 저장값은 다시 계산하지 않는다")
    doc = svc.store.read(day) if hasattr(svc.store, "read") else json.loads((svc.store.path_for(day)).read_text(encoding="utf-8"))
    as_of = datetime.fromisoformat(doc["snapshot"]["as_of"].replace("Z", "+00:00"))
    ck = doc["cockpit"]; now = ck["market_now"]; sel = now.get("selection") or {}
    hist = market_history(_window(mgr, "market_regime", as_of, mgr.window_days), as_of=as_of, days=mgr.window_days,
                          lead_in=_lead_in(mgr, "market_regime", as_of, mgr.window_days))
    lp = hist.points[-1]
    assert lp.as_of == as_of, f"{day}: 마지막 history 행이 이 저장본의 판정이 아니다 ({lp.as_of} ≠ {as_of})"
    tax = {k: str(v["key"]) for k, v in (hcfg.get("taxonomy") or {}).items()}
    cand_state = lp.label.value if hasattr(lp.label, "value") else str(lp.label)
    obs = RSM.Observation(date=lp.date.isoformat(), snapshot_date=day.isoformat(), candidate=tax.get(cand_state, cand_state.lower()), candidate_state=cand_state,
                          raw_signal=sel.get("quant_label"), factors=dict(lp.factors or {}), equity_broad=RSM.broad_equity_from_selection(sel))
    rh = build_regime_history(hist, hcfg, as_of=as_of, stored_days=len(hist.points), state_log=log.all(), today_obs=obs)
    st = rh.state
    cap = CAP / f"{day.isoformat()}-backfill"
    # 전환 해설 — 그날 데이터만(이 저장본 + 그날까지의 행)
    tc = None
    if st is not None and st.changed:
        ctx = TR.build_context(doc, st.model_dump(mode="json"), [d.model_dump(mode="json") for d in rh.days])
        if apply:
            (cap / "transition_read_context.json").write_text(json.dumps(ctx, ensure_ascii=False, indent=1), encoding="utf-8")
        sr = cap / "transition_read_session.json"
        tc = TR.write(ctx, client=None, session_read=json.loads(sr.read_text(encoding="utf-8")) if sr.exists() else None)
        if tc is None:
            print(f"  ! {day}: 전환 해설 세션본 없음/검증 실패 — {sr.relative_to(ROOT)} (컨텍스트: transition_read_context.json)")
    entry = RSM.log_entry(RSM.State.from_dict(st.model_dump()), obs, transition_comment=tc) if st is not None else None
    # 화면 섹션 다시 맞추기
    new_h = rh.model_dump(mode="json")
    old_h = ck.get("history") or {}
    hz = {d.get("key"): d for d in old_h.get("drivers") or []}
    for d in new_h.get("drivers") or []:
        o = hz.get(d.get("key"))
        if o:
            d.update({k: o.get(k) for k in ("horizons", "horizon_read", "horizon_label") if k in o})
    new_h["ranges"] = old_h.get("ranges", new_h.get("ranges"))
    for t in new_h.get("transitions") or []:
        if tc and t["date"] == (st.date if st else "") and t.get("kind") != "legacy":
            t["comment"], t["comment_source"] = tc["text"], tc["source"]
    official = rh.official_state_label
    hf = now_history_fields(cfg, rh, label=official, raw_label=str(now.get("raw_label") or official))
    hf["spark"] = [sp.model_dump(mode="json") for sp in hf["spark"]]
    hf["state"] = hf["state"].model_dump(mode="json") if hf.get("state") is not None else None
    # REGIME v2 선택의 persistence 문장 — 새 규칙의 세션본(같은 검증)이 있으면 그것으로
    sel2 = dict(sel)
    rsf = cap / "regime_select_session.json"
    rcf = cap / "regime_select_context.json"
    if sel and rsf.exists() and rcf.exists():
        s_out = json.loads(rsf.read_text(encoding="utf-8")); r_ctx = json.loads(rcf.read_text(encoding="utf-8"))
        prev_st = (log.all().get(st.date) or {}) if st else {}
        logged_prev = [e for d_, e in sorted(log.all().items()) if (e.get("snapshot_date") or "") < day.isoformat()]
        ps = dict((logged_prev[-1].get("state") or {})) if logged_prev else None
        if ps and ps.get("entry_regime"):
            ps["entry_label"] = {str(v["key"]): str(v["label"]) for v in (hcfg.get("taxonomy") or {}).values()}.get(ps["entry_regime"], ps["entry_regime"])
        prev_off = (logged_prev[-1]["state"]["official"] if logged_prev else None)
        if prev_off:
            r_ctx["official_regime"] = {str(v["key"]): str(v["label"]) for v in (hcfg.get("taxonomy") or {}).values()}.get(prev_off, prev_off)
        if ps:
            r_ctx["persistence_hint"] = RS.persistence_hint_v2(r_ctx["official_regime"], ps)
        probs = RS.check_output(s_out, r_ctx)
        if probs:
            print(f"  ! {day}: regime_select 세션본 검증 실패 — {' / '.join(probs)}")
        elif s_out.get("persistence_assessment") != sel.get("persistence_assessment"):
            sel2["persistence_assessment"] = s_out["persistence_assessment"]
            if apply:
                rcf.write_text(json.dumps(r_ctx, ensure_ascii=False, indent=1), encoding="utf-8")
        _ = prev_st
    new_now = {**now, **hf, "label": official, "label_text": LABEL_TEXT[official], "sentence": now_sentence(cfg, now.get("key_variables") or [], str(now.get("raw_label") or official)),
               "selection": sel2 or None}
    ca = ck.get("cross_asset") or {}
    items = [{"key": r["key"], "instrument": r["instrument"], "instrument_label": r.get("instrument_label"), "z": r.get("z")} for r in ca.get("rows") or []]
    rows_ca, confirm, evaluated, rshort = cross_asset_rows(cfg, official, items)
    new_ca = {**ca, "rows": [r.model_dump(mode="json") for r in rows_ca], "confirm": confirm, "evaluated": evaluated, "regime_short": rshort, "current_view": LABEL_TEXT[official],
              "market_read": cross_asset_read(cfg, rows_ca, rshort), **cross_asset_texts(official, rows_ca, confirm, evaluated, rshort)}
    tone = ck.get("tone")
    if tone is not None:
        snap = IntelligenceSnapshot.model_validate(doc["snapshot"])
        t2 = build_market_tone(snap.thermometer, cfg.get("tone", {}) or {}, regime_key=rh.current_regime, regime_label=rh.current_label, history_points=list(hist.points))
        if t2 is not None:
            tone = json.loads(t2.model_dump_json())
    new_ck = {**ck, "history": new_h, "market_now": new_now, "cross_asset": new_ca, "tone": tone}
    new_doc = {**doc, "cockpit": new_ck}
    row = {"S": day.isoformat(), "row": st.date if st else "", "official": st.official if st else "", "candidate": st.candidate if st else "", "raw": st.raw_signal if st else "",
           "support": st.support if st else "", "exit": f"{st.exit_streak}/{st.exit_required}" + (" CONFIRMED" if st and st.exit_confirmed else "") if st and st.official_label else "",
           "entry": (f"{st.entry_label} {st.entry_streak}/{st.entry_required}" + (" CONFIRMED" if st.entry_confirmed else "")) if st and (st.entry_regime or st.entry_confirmed) else "–",
           "status": rh.transition_status, "prev_official": rh.previous_label, "duration": rh.duration_days, "transitions_1m": rh.transitions_1m,
           "before": (old_h.get("current_label"), old_h.get("duration_days"), old_h.get("transitions_1m")), "comment": (tc or {}).get("text")}
    if apply:
        if entry is not None:
            if not log.put_once(entry):
                print(f"  = {day}: 상태 로그 {st.date} 가 이미 있다 — 그대로 둔다")
        (cap / "cockpit.json").write_text(json.dumps(new_ck, ensure_ascii=False), encoding="utf-8")
    return {"row": row, "doc": new_doc}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dates", nargs="+")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--reason", default="")
    ap.add_argument("--by", default="")
    a = ap.parse_args()
    days = sorted(date.fromisoformat(x) for x in a.dates)  # 오름차순 고정
    st_ = get_settings()
    svc = DailyArchiveService(ArchiveStore(st_.archive_dir))
    mgr = DailySnapshotManager(JsonDirStore(st_.history_dir))
    log = RSM.RegimeStateLog(st_.regime_state_dir)
    cfg = load_cockpit_config(None)
    if a.apply and not a.reason:
        raise SystemExit("--apply 에는 --reason 이 필요하다(archive correct)")
    if not a.apply:
        # 미리 보기는 로그를 쓰지 않으므로 임시 로그에 차례로 쌓아 뒤 날짜가 앞 날짜 상태를 잇게 한다
        import shutil, tempfile
        tmp = Path(tempfile.mkdtemp(prefix="rs-preview-"))
        if st_.regime_state_dir.exists():
            shutil.copytree(st_.regime_state_dir, tmp / "rs")
        log = RSM.RegimeStateLog(tmp / "rs")
    for d in days:
        res = process(d, svc=svc, mgr=mgr, log=log, cfg=cfg, apply=a.apply)
        if not a.apply:
            # 다음 날짜가 잇도록 임시 로그에만 쓴다
            r = res["row"]
            hist_state = res["doc"]["cockpit"]["history"]["state"]
            if hist_state:
                log.put_once({"date": hist_state["date"], "snapshot_date": hist_state["snapshot_date"], "state": hist_state,
                              "observation": {"candidate": hist_state["candidate"], "raw_signal": hist_state.get("raw_signal")}})
        print(json.dumps(res["row"], ensure_ascii=False))
        if a.apply:
            final, keep = svc.correct(d, res["doc"], reason=a.reason, by=a.by)
            print(f"  → correction {final.relative_to(ROOT)} (이전 파일 {keep.relative_to(ROOT)})")


if __name__ == "__main__":
    main()
