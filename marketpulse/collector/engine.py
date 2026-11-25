"""
입력 수집 엔진 — Daily Snapshot 이 읽는 입력 폴더를 만든다. Claude 없이 Python 만으로 돈다 (2026-11-25).

만드는 것(기존 `archive fetch-inputs` 와 같은 파일 · 같은 형식 — 읽는 쪽 코드는 그대로다):

    <out>/series_base.json · series_universe.json · series_basket.json     계열(공급자 응답 그대로)
    <out>/news_rss.json                                                     RSS 기사(여러 번 받은 것을 id 로 합친다)
    <out>/collect_status.json                                               계열별 상태 · 공급처별 성공/실패 · 회로 상태 · 다음 시도 시각
    <out>/checkpoint/<묶음>/<id>.json                                        계열 하나를 받을 때마다 남긴다 — 이어 받기의 근거

기존 수집과 다른 점은 넷이다.

  1. 계열을 하나 받을 때마다 파일로 남긴다. 프로세스 · 컨테이너가 죽어도 다시 실행하면 **빠진 계열만** 받는다.
  2. 공급처가 막히면 그 공급처를 쉬게 하고(adapters/breaker.py — 상태가 파일에 남는다) 그 계열은 다음 공급처로 넘어간다.
     넘어갈 곳이 없으면 결측으로 남긴다. 한 공급처의 장애가 다른 공급처 수집을 막지 않는다.
  3. 기다리는 시간에 상한이 있다(run.budget_min). 상한을 넘으면 받은 데까지 저장하고 끝낸다 — 종료 코드 75 와
     '다음에 다시 시도할 수 있는 시각' 을 남긴다. 스케줄러(cron · 작업 스케줄러)가 그 뒤에 다시 부르면 이어 받는다.
  4. 대체 공급처에서 받은 계열은 직전 수집분과 값을 대조한 뒤에만 쓴다(단위 · 수정주가 불일치를 걸러 낸다).

만들지 않는 것: 값. 0 · 보간 · 전날 값 채우기는 없다. 전날 수집분은 대조에만 쓰고 오늘 입력에 합치지 않는다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from ..archive.input_status import assess, load_collection_config
from ..models.market import MarketSeries

REPO = Path(__file__).resolve().parents[2]
PKG = REPO / "marketpulse"
KST = ZoneInfo("Asia/Seoul")
GROUPS = ("base", "universe", "basket")

EXIT_OK = 0
EXIT_INCOMPLETE = 75  # EX_TEMPFAIL — 나중에 다시 부르면 이어 받는다
EXIT_LOCKED = 73


def state_dir() -> Path:
    """회로 상태가 사는 곳. 컨테이너 재시작에도 남는 디스크 경로여야 한다(기본: 저장소 폴더 아래, git 에는 넣지 않는다)."""
    return Path(os.environ.get("MARKETPULSE_STATE_DIR") or REPO / ".marketpulse_state")


def inputs_root() -> Path:
    return Path(os.environ.get("MARKETPULSE_INPUTS_DIR") or PKG / "data" / "inputs")


def kst_today(now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(KST).date()


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, doc: Any, *, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=indent), encoding="utf-8")
    os.replace(tmp, path)


# ── 무엇을 받는가 ─────────────────────────────────────────
@dataclass
class Plan:
    group: str
    instruments: list[Any]                      # 직접 받는 계열(파생 제외)
    derived: list[Any] = field(default_factory=list)
    sources: dict[str, list[Any]] | None = None  # 종목 · 바스켓은 계열별 공급처 순서. 기본 묶음은 sources.yaml(None)
    bars: int = 300
    specs: dict[str, list[dict]] = field(default_factory=dict)  # 계열별 시도 순서(목록 · 보고용)

    @property
    def expected(self) -> list[str]:
        return [i.id for i in self.instruments] + [i.id for i in self.derived]


def _fallback_specs(symbol: str, cfg: Mapping[str, Any]) -> list[dict]:
    out: list[dict] = []
    for rule in (cfg.get("fallbacks") or {}).values():
        if re.match(str(rule.get("match") or "$^"), symbol):
            for s in rule.get("sources") or []:
                out.append({"provider": s["provider"], "symbol": str(s["symbol"]).format(symbol=symbol, lower=symbol.lower())})
    return out


def build_plans(settings=None, cfg: Mapping[str, Any] | None = None) -> dict[str, Plan]:
    """세 묶음의 수집 대상과 공급처 순서. 대상은 `archive fetch-inputs` 와 같다 — 종목 · 바스켓에 대체 공급처 순서만 더 붙는다."""
    from ..adapters.market.live import load_sources
    from ..config.registry import get_instruments, get_universe
    from ..config.settings import Settings
    from ..engines.ai_regime import basket_instruments
    from ..engines.investment import shared_driver_ids
    from ..models.intelligence import AltInstrument, SourceSpec

    settings = settings or Settings(data_mode="DELAYED", llm_enabled=False, news_search="off")
    cfg = cfg or load_collection_config()
    src_yaml = load_sources(settings.config_dir)

    ins = get_instruments().instruments
    base = Plan("base", [i for i in ins if i.derived_from is None], [i for i in ins if i.derived_from is not None], None, settings.history_bars,
                {i.id: [dict(s) for s in src_yaml.get(i.id, [])] for i in ins if i.derived_from is None})

    u = get_universe(settings.config_dir)
    base_ins = get_instruments().by_id()
    shared = [base_ins[i] for i in shared_driver_ids(settings.config_dir)]
    sources: dict[str, list[Any]] = {a.id: list(a.sources) for a in u.alternative}
    for s in u.stocks:
        sources[s.id] = [SourceSpec(provider="yahoo", symbol=s.symbol)] + [SourceSpec(**f) for f in _fallback_specs(str(s.symbol), cfg)]
    uni_ins = [s.as_instrument() for s in u.stocks] + [a.as_instrument() for a in u.alternative] + shared
    alt_providers = {"yahoo", "stooq", "twelvedata", "csv"}
    uni_specs = {i.id: [s.model_dump() for s in sources[i.id]] if i.id in sources else [dict(s) for s in src_yaml.get(i.id, []) if s.get("provider") in alt_providers] for i in uni_ins}
    universe = Plan("universe", uni_ins, [], sources, settings.history_bars, uni_specs)

    members = []
    bsources: dict[str, list[Any]] = {}
    for m in basket_instruments():
        sym = str(m["symbol"])
        a = AltInstrument(id=m["id"], name=m.get("name", m["id"]), group="ai", asset_class="equity", unit="price",
                          sources=[SourceSpec(provider="yahoo", symbol=sym)] + [SourceSpec(**f) for f in _fallback_specs(sym, cfg)], source_type="EXCHANGE")
        members.append(a.as_instrument())
        bsources[a.id] = list(a.sources)
    basket = Plan("basket", members, [], bsources, 120, {k: [s.model_dump() for s in v] for k, v in bsources.items()})
    return {"base": base, "universe": universe, "basket": basket}


# ── 대체 공급처 대조 ───────────────────────────────────────
def validate_against_reference(series: MarketSeries, ref: MarketSeries | None, cfg: Mapping[str, Any]) -> tuple[str, str]:
    """
    대체 공급처에서 받은 계열을 직전 수집분과 대조한다. ("OK" | "NO_REFERENCE" | "REJECT", 설명).
    겹치는 날짜의 값만 본다 — 직전 수집분의 값을 오늘 계열에 넣지는 않는다.
    """
    v = cfg.get("validate") or {}
    if ref is None or not ref.timestamps:
        return "NO_REFERENCE", "대조할 직전 수집분이 없다"
    a = {t.date(): x for t, x in zip(series.timestamps, series.values)}
    b = {t.date(): x for t, x in zip(ref.timestamps, ref.values)}
    days = sorted(set(a) & set(b))[-int(v.get("overlap_bars", 20)):]
    diffs = sorted(abs(a[d] / b[d] - 1.0) for d in days if b[d])
    if len(diffs) < int(v.get("min_overlap", 5)):
        return "NO_REFERENCE", f"겹치는 봉 {len(diffs)}개 — 판단하지 않는다"
    med = diffs[len(diffs) // 2]
    if med > float(v.get("max_median_rel_diff", 0.02)):
        return "REJECT", f"직전 수집분({ref.meta.source})과 겹치는 {len(diffs)}봉의 차이 중앙값 {med:.1%} — 단위 · 수정주가 · 통화 불일치 의심"
    return "OK", f"직전 수집분({ref.meta.source})과 겹치는 {len(diffs)}봉의 차이 중앙값 {med:.2%}"


def find_reference(day: date, root: Path | None = None) -> Path | None:
    """대조 기준 — 그 날짜보다 앞선 가장 최근 수집 폴더."""
    root = root or inputs_root()
    if not root.is_dir():
        return None
    prior = sorted(p for p in root.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name) and p.name < day.isoformat() and (p / "series_base.json").is_file())
    return prior[-1] if prior else None


# ── 수집기 ────────────────────────────────────────────────
class Collector:
    def __init__(self, day: date, out: Path, *, cfg: Mapping[str, Any] | None = None, settings=None, reference: Path | None = None,
                 client=None, breaker=None, now: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
                 log: Callable[[str], None] = print, plans: Mapping[str, Plan] | None = None, adapters: tuple[Any, Any] | None = None) -> None:
        from ..config.settings import Settings

        self.day, self.out = day, Path(out)
        self.cfg = dict(cfg or load_collection_config())
        self.run_cfg = dict(self.cfg.get("run") or {})
        self.settings = settings or Settings(data_mode="DELAYED", llm_enabled=False, news_search="off")
        self._now, self._sleep, self.log = now, sleep, log
        self.reference = reference
        self.out.mkdir(parents=True, exist_ok=True)
        self.status_path = self.out / "collect_status.json"
        self.status = self._load_status()
        self.plans = dict(plans or build_plans(self.settings, self.cfg))
        self.status["expected"] = {g: p.expected for g, p in self.plans.items()}
        if breaker is None:
            from ..adapters.breaker import ProviderBreaker
            breaker = ProviderBreaker(state_dir() / "provider_breaker.json", config=self.cfg.get("breaker"), now=now)
        self.breaker = breaker
        if adapters is not None:
            self.client, (self.market, self.alt) = client, adapters
        else:
            self.client, self.market, self.alt = self._make_adapters(client)
        self._ref_cache: dict[str, dict[str, MarketSeries]] = {}
        self._seed_checkpoints()

    def _seed_checkpoints(self) -> None:
        """다른 곳에서 수집해 넘겨받은 폴더(series_*.json 만 있다)면 계열별 체크포인트를 만들어 둔다 — 빠진 계열만 이어 받을 수 있게."""
        for g in GROUPS:
            f, d = self.out / f"series_{g}.json", self.out / "checkpoint" / g
            if d.is_dir() or not f.is_file():
                continue
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            for iid, v in doc.items():
                if str(((v.get("meta") or {}).get("source")) or "").lower().startswith("derived:"):
                    continue
                _write_json(d / f"{iid}.json", v)

    # ── 준비 ──────────────────────────────────────────────
    def _make_adapters(self, client):
        from ..adapters.alternative.live import AltLiveAdapter
        from ..adapters.http import BreakerHttpClient
        from ..adapters.market.live import LiveMarketAdapter
        from ..models.common import DataMode

        if client is None:
            client = BreakerHttpClient(timeout_sec=max(float(self.settings.http_timeout_sec), 12.0), min_gap_sec=float(self.run_cfg.get("min_gap_sec", 2.0)), breaker=self.breaker)
            client._gap.update({str(h): float(g) for h, g in (self.cfg.get("host_min_gap_sec") or {}).items()})
            client._sleep = self._sleep  # type: ignore[method-assign]
        market = LiveMarketAdapter(replay_dir=self.settings.replay_dir, config_dir=self.settings.config_dir, mode=DataMode.DELAYED, client=client)
        alt = AltLiveAdapter(replay_dir=self.settings.replay_dir, config_dir=self.settings.config_dir, client=client, store=None)
        alt.politeness_sec = 0.0
        return client, market, alt

    def _load_status(self) -> dict[str, Any]:
        try:
            doc = json.loads(self.status_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = {}
        if doc.get("day") not in (None, self.day.isoformat()):
            raise RuntimeError(f"{self.out} 은 {doc.get('day')} 수집 폴더다 — {self.day} 수집에 다시 쓰지 않는다(전날 수집분을 오늘 입력에 섞지 않는다)")
        doc.setdefault("schema", 1)
        doc["day"] = self.day.isoformat()
        doc.setdefault("runs", [])
        doc.setdefault("series", {g: {} for g in GROUPS})
        doc.setdefault("providers", {})
        return doc

    def _save_status(self) -> None:
        self.status["updated_at"] = _iso(datetime.fromtimestamp(self._now(), tz=timezone.utc))
        self.status["breaker"] = self.breaker.snapshot()
        self.status["next_retry_at"] = self.breaker.next_retry_at()
        _write_json(self.status_path, self.status, indent=1)

    # ── 잠금(같은 폴더에 두 번 돌지 않게) ───────────────────
    LOCK_STALE_SEC = 120.0  # 수집 중에는 30초 안쪽으로 맥박을 남긴다 — 이보다 오래 조용하면 죽은 것으로 본다

    def _lock(self) -> bool:
        """
        같은 폴더에서 다른 수집이 돌고 있으면 False. 죽은 수집이 남긴 잠금은 넘겨받는다 —
        컨테이너가 재시작되면 그 프로세스는 없으므로(POSIX: pid 확인) 바로 이어 받고, pid 를 확인할 수 없는 곳(Windows)에서는 맥박이 끊긴 지 2분이면 넘겨받는다.
        """
        p = self.out / ".lock"
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            beat, pid = float(doc.get("beat", 0)), int(doc.get("pid", 0))
            alive = self._now() - beat < self.LOCK_STALE_SEC
            if alive and os.name != "nt" and pid and pid != os.getpid():
                try:
                    os.kill(pid, 0)  # 신호를 보내지 않고 있는지만 본다
                except ProcessLookupError:
                    alive = False
                except OSError:
                    pass
            if alive and pid != os.getpid():
                return False
        except (OSError, ValueError):
            pass
        self._beat()
        return True

    def _wait(self, sec: float) -> None:
        """기다리는 동안에도 맥박을 남긴다."""
        left = max(0.0, sec)
        while left > 0:
            step = min(30.0, left)
            self._sleep(step)
            left -= step
            self._beat()

    def _beat(self) -> None:
        _write_json(self.out / ".lock", {"pid": os.getpid(), "beat": self._now()})

    def _unlock(self) -> None:
        try:
            (self.out / ".lock").unlink()
        except OSError:
            pass

    # ── 체크포인트 ────────────────────────────────────────
    def _cp(self, group: str, iid: str) -> Path:
        return self.out / "checkpoint" / group / f"{iid}.json"

    def have(self, group: str, iid: str) -> bool:
        return self._cp(group, iid).is_file()

    def load_group(self, group: str) -> dict[str, MarketSeries]:
        d = self.out / "checkpoint" / group
        out: dict[str, MarketSeries] = {}
        for p in sorted(d.glob("*.json")) if d.is_dir() else []:
            try:
                out[p.stem] = MarketSeries.model_validate_json(p.read_text(encoding="utf-8"))
            except ValueError:
                p.unlink()  # 쓰다 끊긴 파일 — 다시 받는다
        return out

    def _ref(self, group: str, iid: str) -> MarketSeries | None:
        if self.reference is None:
            return None
        if group not in self._ref_cache:
            f = self.reference / f"series_{group}.json"
            try:
                self._ref_cache[group] = {k: MarketSeries.model_validate(v) for k, v in json.loads(f.read_text(encoding="utf-8")).items()}
            except (OSError, ValueError):
                self._ref_cache[group] = {}
        return self._ref_cache[group].get(iid)

    # ── 계열 하나 ─────────────────────────────────────────
    def _count(self, provider: str, key: str) -> None:
        row = self.status["providers"].setdefault(provider, {"ok": 0, "failed": 0, "circuit_skipped": 0, "unavailable": 0})
        row[key] = row.get(key, 0) + 1

    def fetch_one(self, plan: Plan, ins, as_of: datetime) -> str:
        """계열 하나를 받는다. 돌려주는 상태: OK · DEFERRED(공급처 회로가 열려 못 보냄 — 나중에 다시) · FAILED · REJECTED."""
        g, iid = plan.group, ins.id
        row = self.status["series"][g].setdefault(iid, {"tries": 0})
        if plan.sources is None:
            got = self.market.fetch_series([ins], bars=plan.bars, as_of=as_of)
            outcome = self.market.outcomes.get(iid)
        else:
            got = self.alt.fetch_series([ins], {iid: plan.sources.get(iid) or []} if iid in plan.sources else {}, bars=plan.bars, as_of=as_of)
            outcome = self.alt.outcomes.get(iid)
        attempts = [list(a) for a in (getattr(outcome, "attempts", None) or [])]
        deferred = False
        for name, why in attempts:
            if "회로 열림" in why:
                deferred = True
                self._count(name, "circuit_skipped")
            elif "가 없다" in why and "API_KEY" in why:
                self._count(name, "unavailable")
            else:
                self._count(name, "failed")
        row["attempts"] = attempts
        row["at"] = _iso(as_of)
        series = got.get(iid)
        if series is None:
            if deferred:
                row["state"] = "DEFERRED"
            else:
                row["tries"] = int(row.get("tries", 0)) + 1
                row["state"] = "FAILED"
            return row["state"]
        provider = str(getattr(outcome, "provider", "") or "")
        first = str((plan.specs.get(iid) or [{}])[0].get("provider") or provider)
        row.update(provider=provider, source=str(series.meta.source), points=len(series.timestamps),
                   last_bar=series.timestamps[-1].isoformat() if series.timestamps else None)
        row["tries"] = int(row.get("tries", 0)) + 1
        if provider and provider != first and provider not in ("csv", "csv_base"):
            verdict, note = validate_against_reference(series, self._ref(g, iid), self.cfg)
            row["alt_source"] = {"primary": first, "used": provider, "check": verdict, "note": note}
            if verdict == "REJECT":
                self._count(provider, "failed")
                row["state"] = "REJECTED"
                return "REJECTED"
        self._count(provider or "unknown", "ok")
        _write_json(self._cp(g, iid), json.loads(series.model_dump_json()))
        row["state"] = "OK"
        return "OK"

    def refetch_stale(self, groups: tuple[str, ...], t0: float, budget: float) -> list[str]:
        """
        앞선 실행에서 받았지만 마지막 봉이 빠져 있던 계열(STALE)을 한 번 더 받는다 — 공급처가 최신 일봉 없이 응답하는 날이 있다.
        새로 받은 쪽의 마지막 봉이 더 늦을 때만 바꾼다. 아니면 앞서 받은 것을 그대로 둔다(같은 날 수집분끼리만 — 값은 손대지 않는다).
        """
        stale = (self.status.get("input_status") or {}).get("stale") or {}
        mx = int(self.run_cfg.get("max_tries_per_series", 4))
        done: list[str] = []
        for g in groups:
            plan = self.plans[g]
            by_id = {i.id: i for i in plan.instruments}
            for iid in stale.get(g) or []:
                ins, row = by_id.get(iid), self.status["series"][g].get(iid) or {}
                if ins is None or not self.have(g, iid) or int(row.get("tries", 0)) >= mx or self._now() - t0 > budget:
                    continue
                if str(row.get("provider")) in ("csv", "csv_base", "github"):
                    continue  # 원래 늦는 경로 — 다시 받아도 같다
                cp = self._cp(g, iid)
                old_text, old_row = cp.read_text(encoding="utf-8"), dict(row)
                old_last = MarketSeries.model_validate_json(old_text).timestamps[-1]
                cp.unlink()
                state = self.fetch_one(plan, ins, datetime.fromtimestamp(self._now(), tz=timezone.utc))
                newer = state == "OK" and MarketSeries.model_validate_json(cp.read_text(encoding="utf-8")).timestamps[-1] > old_last
                if newer:
                    done.append(f"{g}:{iid}")
                else:
                    cp.write_text(old_text, encoding="utf-8")
                    self.status["series"][g][iid] = {**old_row, "tries": int(self.status["series"][g][iid].get("tries", 0)), "refetch": "새 봉 없음 — 앞서 받은 것을 둔다"}
                self._beat()
                self._save_status()
        if done:
            self.log(f"마지막 봉이 빠져 있던 계열 {len(done)}개를 새로 받았다: {', '.join(done)[:300]}")
        return done

    def pending(self, plan: Plan, *, include_deferred: bool = True) -> list[Any]:
        mx = int(self.run_cfg.get("max_tries_per_series", 4))
        out = []
        for ins in plan.instruments:
            if self.have(plan.group, ins.id):
                continue
            row = self.status["series"][plan.group].get(ins.id) or {}
            if int(row.get("tries", 0)) >= mx:
                continue
            if row.get("state") == "DEFERRED" and not include_deferred:
                continue
            out.append(ins)
        return out

    # ── 조립 ──────────────────────────────────────────────
    def assemble(self) -> dict[str, dict[str, int]]:
        """체크포인트로 series_*.json 을 다시 쓴다. 기본 묶음의 파생 계열은 받은 재료로 계산한다(네트워크 없음)."""
        from ..archive.reconstruct import _dump_series

        counts: dict[str, dict[str, int]] = {}
        for g, plan in self.plans.items():
            series = self.load_group(g)
            if plan.derived:
                derived = self.market.derive_series(list(plan.instruments) + list(plan.derived), series)
                for i in plan.derived:
                    row = self.status["series"][g].setdefault(i.id, {"tries": 0})
                    oc = self.market.outcomes.get(i.id)
                    if i.id in derived:
                        row.update(state="OK", provider="derived", source=str(derived[i.id].meta.source), points=len(derived[i.id].timestamps),
                                   last_bar=derived[i.id].timestamps[-1].isoformat())
                    else:
                        row.update(state="FAILED", attempts=[list(a) for a in (getattr(oc, "attempts", None) or [])])
                series.update(derived)
            _dump_series(self.out / f"series_{g}.json", series)
            counts[g] = {"got": len(series), "of": len(plan.expected)}
        return counts

    # ── 기사 ──────────────────────────────────────────────
    def collect_news(self, limit: int = 500) -> dict[str, Any]:
        """RSS 를 지금 받아 이 폴더의 news_rss.json 과 id 로 합친다(07:30 KST 전후로 여러 번 불러도 된다). 기사 내용은 손대지 않는다."""
        from ..adapters.registry import build_news_adapter
        from ..models.common import utcnow

        path = self.out / "news_rss.json"
        try:
            merged = {str(i.get("id")): i for i in json.loads(path.read_text(encoding="utf-8"))}
        except (OSError, ValueError):
            merged = {}
        before = len(merged)
        try:
            fresh = [i.model_dump(mode="json") for i in build_news_adapter(self.settings).fetch_news(limit=limit, as_of=utcnow())]
            err = None
        except Exception as exc:  # noqa: BLE001 — 기사는 없어도 가격 수집은 계속한다
            fresh, err = [], f"{type(exc).__name__}: {exc}"
        for it in fresh:
            merged[str(it.get("id"))] = it
        items = sorted(merged.values(), key=lambda x: str(x.get("published_at") or ""))
        _write_json(path, items)
        info = {"at": _iso(datetime.fromtimestamp(self._now(), tz=timezone.utc)), "fresh": len(fresh), "new": len(merged) - before, "total": len(items), "error": err,
                "last": items[-1].get("published_at") if items else None}
        self.status["news"] = info
        return info

    # ── 실행 ──────────────────────────────────────────────
    def run(self, *, groups: tuple[str, ...] = GROUPS, news: bool = True, budget_sec: float | None = None, wait: bool | None = None) -> int:
        if not self._lock():
            self.log(f"{self.out} 에서 다른 수집이 돌고 있다 — 끝낸다")
            return EXIT_LOCKED
        t0 = self._now()
        budget = float(budget_sec if budget_sec is not None else float(self.run_cfg.get("budget_min", 25)) * 60)
        wait = bool(self.run_cfg.get("wait_for_breaker", True)) if wait is None else wait
        run = {"started_at": _iso(datetime.fromtimestamp(t0, tz=timezone.utc)), "groups": list(groups), "fetched": 0, "rounds": 0}
        self.status["runs"].append(run)
        try:
            if self.reference is None:
                self.reference = find_reference(self.day, self.out.parent)
            self.status["reference"] = str(self.reference) if self.reference else None
            if news:
                n = self.collect_news()
                self.log(f"기사 {n['total']}건(새로 {n['new']}건){' · 오류 ' + n['error'] if n['error'] else ''}")
            run["refetched_stale"] = self.refetch_stale(groups, t0, budget)
            include_deferred = True
            while True:
                run["rounds"] += 1
                out_of_time = False
                for g in groups:
                    plan = self.plans[g]
                    todo = self.pending(plan, include_deferred=include_deferred)
                    if todo:
                        self.log(f"[{g}] 받을 계열 {len(todo)}개 (이미 받은 것 {len(plan.instruments) - len(self.pending(plan))}개)")
                    for ins in todo:
                        if self._now() - t0 > budget:
                            out_of_time = True
                            break
                        as_of = datetime.fromtimestamp(self._now(), tz=timezone.utc)
                        state = self.fetch_one(plan, ins, as_of)
                        run["fetched"] += state == "OK"
                        if state != "OK":
                            why = " / ".join(f"{a} {b}" for a, b in (self.status["series"][g][ins.id].get("attempts") or []))[:200]
                            self.log(f"[{g}] {ins.id} {state} — {why or self.status['series'][g][ins.id].get('alt_source')}")
                        self._beat()
                        self._save_status()
                    if out_of_time:
                        break
                counts = self.assemble()
                left = {g: len(self.pending(self.plans[g])) for g in groups}
                self._save_status()
                if out_of_time or not any(left.values()):
                    break
                nxt = self.breaker.next_retry_at()
                if nxt is None:  # 회로는 닫혀 있다 — 남은 것은 방금 실패한 계열이다. 같은 실행에서 곧바로 되풀이하지 않는다
                    break
                remain = budget - (self._now() - t0)
                gap = datetime.fromisoformat(nxt.replace("Z", "+00:00")).timestamp() - self._now()
                if not wait or gap + 5 > remain:
                    self.log(f"회로가 {nxt} 까지 열려 있다 — 남은 예산({remain:.0f}초) 밖이라 기다리지 않고 끝낸다")
                    break
                self.log(f"회로가 {nxt} 까지 열려 있다 — {gap:.0f}초 뒤 이어 받는다")
                self._wait(max(gap, 0) + 1)
                include_deferred = True
            counts = self.assemble()
            left = {g: len(self.pending(self.plans[g])) for g in GROUPS}
            run.update(finished_at=_iso(datetime.fromtimestamp(self._now(), tz=timezone.utc)), elapsed_sec=round(self._now() - t0), counts=counts, pending=left,
                       http=dict(getattr(self.client, "stats", {}) or {}))
            self.status["complete"] = not any(left.values())
            self._write_input_status()
            self._save_status()
            self._write_fetch_report(counts)
            self.log(json.dumps({"counts": counts, "pending": left, "next_retry_at": self.breaker.next_retry_at(), "elapsed_sec": run["elapsed_sec"]}, ensure_ascii=False))
            return EXIT_OK if self.status["complete"] else EXIT_INCOMPLETE
        finally:
            self._unlock()

    def _write_input_status(self) -> None:
        """그날 07:30 KST 기준으로 받은 계열의 OK · STALE · MISSING 과 FULL / PARTIAL 판정을 같이 남긴다(읽는 쪽이 바로 본다)."""
        from ..archive.reconstruct import cutoff_for

        try:
            st = assess(self.out, cutoff_for(self.day), expected=self.status["expected"], cfg=self.cfg)
        except Exception as exc:  # noqa: BLE001 — 판정 실패가 수집 결과를 버리게 하지 않는다
            self.status["input_status_error"] = f"{type(exc).__name__}: {exc}"
            return
        _write_json(self.out / "input_status.json", st, indent=1)
        self.status["input_status"] = {k: st[k] for k in ("cutoff", "counts", "gate", "closed_suspect", "stale")}

    def _write_fetch_report(self, counts: Mapping[str, Mapping[str, int]]) -> None:
        """기존 fetch_report.json 과 같은 모양(got · of · failed) — 이 파일을 읽던 도구가 그대로 돈다."""
        rep: dict[str, Any] = {"fetched_at": self.status.get("updated_at"), "collector": "marketpulse.collector"}
        for g, plan in self.plans.items():
            have = set(json.loads((self.out / f"series_{g}.json").read_text(encoding="utf-8")))
            failed = []
            for iid in plan.expected:
                if iid not in have:
                    row = self.status["series"][g].get(iid) or {}
                    failed.append([iid, " / ".join(f"{a} {b}" for a, b in (row.get("attempts") or [])) or row.get("state") or "아직 시도하지 않았다"])
            rep[g] = {"got": counts[g]["got"], "of": counts[g]["of"], "failed": failed}
        rep["http"] = dict(getattr(self.client, "stats", {}) or {})
        rep["news"] = (self.status.get("news") or {}).get("total")
        _write_json(self.out / "fetch_report.json", rep, indent=1)


def prune(root: Path, keep_days: int, today: date) -> list[str]:
    """오래된 수집 폴더를 지운다(대조 기준으로 최근 keep_days 개만 남긴다). 날짜 이름 폴더만 건드린다."""
    if not root.is_dir() or keep_days <= 0:
        return []
    days = sorted(p for p in root.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name) and p.name <= today.isoformat())
    gone = []
    for p in days[:-keep_days]:
        shutil.rmtree(p, ignore_errors=True)
        gone.append(p.name)
    return gone
