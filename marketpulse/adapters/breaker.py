"""
공급처 단위 Circuit Breaker — 상태가 파일에 남는다 (2026-11-25).

왜 따로 두는가. HttpClient 의 회로는 프로세스 메모리에만 있다. 프로세스나 컨테이너가 다시 뜨면 '방금 막혔다' 는 사실을
잊고 같은 공급처를 처음부터 다시 두드린다. 2026-11-25 아침이 그랬다 — Yahoo 가 429 를 주는 동안 8분마다 깨어나는
대기 작업이 두 시간 넘게 같은 요청을 되풀이했고, 컨테이너가 재시작되자 그것도 처음부터 다시 걸렸다.

여기서는 셋을 지킨다.

  1. 공급처(호스트) 전체에 건다. 계열 하나가 429 를 받으면 그 공급처의 다른 계열도 같은 쉬는 시간을 지킨다.
  2. 쉬는 시간은 공급처가 말한 대로(Retry-After). 말이 없으면 연속 실패마다 짧게 쉬고(backoff), 임계에 닿으면
     회로를 열어 base → 2배 → … → max 로 늘린다(Exponential Backoff). 회로가 열려 있는 동안에는 요청을 보내지 않는다.
  3. 상태를 JSON 파일에 원자적으로 쓴다. 다시 뜬 프로세스는 파일을 읽어 남은 쉬는 시간을 그대로 이어 간다(벽시계 기준).

기다리지 않는다. 회로가 열리면 호출자는 곧바로 실패를 돌려받아 다음 공급처로 넘어가거나 그 계열을 결측으로 남긴다.
'언제 다시 시도할 수 있는지' 는 snapshot() 의 open_until 로 알려 준다 — 스케줄러가 그 뒤에 다시 부르면 된다.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Mapping

#: 쉬라는 뜻의 응답 — 호출량 제한
THROTTLE_KINDS = frozenset({"http_429", "http_503"})
#: 공급처에 닿지 못함 — 연결 실패 · 무응답
OUTAGE_KINDS = frozenset({"network", "timeout"})

DEFAULTS: dict[str, Any] = {
    "threshold": 3,                 # 연속 실패가 이만큼 쌓이면 회로를 연다
    "half_open_failures": 1,        # 쉬는 시간이 끝난 뒤 시험 요청이 이만큼 연속 실패하면 다시 연다(쉬는 시간 2배)
    "backoff_sec": [10.0, 20.0],    # 회로를 열기 전, 연속 실패 1 · 2번째 뒤에 공급처 전체가 쉬는 시간
    "base_cooldown_sec": 300.0,     # 회로를 처음 열 때 쉬는 시간
    "max_cooldown_sec": 3600.0,     # 2배씩 늘리는 상한
    "retry_after_cap_sec": 21600.0, # 공급처가 말한 Retry-After 를 따르되 이보다 길게는 잡지 않는다
    "close_after_successes": 5,     # 회로가 닫힌 뒤 이만큼 연속 성공하면 '몇 번 열렸는지' 를 0 으로 돌린다
    "reset_opens_after_sec": 21600.0,  # 쉬는 시간이 끝나고 이만큼 지나도록 다시 열리지 않았으면 '몇 번 열렸는지' 를 0 으로 돌린다
    "max_events": 60,
}


def parse_retry_after(value: str | None, *, now: float | None = None) -> float | None:
    """Retry-After 헤더 → 초. 숫자(초) 또는 HTTP 날짜. 못 읽으면 None(없는 것으로 본다 — 지어내지 않는다)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        sec = float(text)
        return max(0.0, sec)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, when.timestamp() - (time.time() if now is None else now))


def _iso(ts: float | None) -> str | None:
    return None if ts is None else datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


class ProviderBreaker:
    def __init__(self, path: Path | str, *, config: Mapping[str, Any] | None = None, now: Callable[[], float] = time.time) -> None:
        self.path = Path(path)
        self.cfg = {**DEFAULTS, **dict(config or {})}
        self._now = now
        self._doc: dict[str, Any] = {"schema": 1, "hosts": {}}
        self._load()

    # ── 파일 ──────────────────────────────────────────────
    def _load(self) -> None:
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and isinstance(doc.get("hosts"), dict):
                self._doc = doc
        except (OSError, ValueError):
            pass  # 없거나 깨졌으면 닫힌 상태로 시작한다(깨진 파일은 다음 쓰기에서 바뀐다)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(self._doc, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def _host(self, host: str) -> dict[str, Any]:
        return self._doc["hosts"].setdefault(host, {"state": "closed", "consecutive": 0, "opens": 0, "successes": 0,
                                                    "open_until": None, "pause_until": None, "events": []})

    def _event(self, h: dict[str, Any], **kw: Any) -> None:
        h["events"] = (h.get("events") or [])[-(int(self.cfg["max_events"]) - 1):] + [{"at": _iso(self._now()), **kw}]

    # ── 판단 ──────────────────────────────────────────────
    def allow(self, host: str) -> tuple[bool, str]:
        """지금 이 공급처에 요청을 보내도 되는가. 열려 있으면 (False, 이유). 쉬는 시간이 끝났으면 시험 요청 하나를 허락한다(half-open)."""
        self._load()  # 다른 프로세스가 바꿨을 수 있다 — 파일이 진실이다
        h = self._host(host)
        now = self._now()
        if h["state"] == "open":
            until = float(h.get("open_until") or 0.0)
            if now < until:
                return False, f"회로 열림 — {_iso(until)} 까지 쉼(남은 {until - now:.0f}초) · 직전 {h.get('last_error')}"
            h["state"] = "half_open"
            h["consecutive"] = 0  # 시험 요청의 연속 실패는 새로 센다
            # 쉬는 시간이 끝난 지 오래됐으면(기본 6시간) '몇 번 열렸는지' 를 잊는다 — 어제 아침의 누적이 오늘 첫 실패를 1시간짜리로 만들지 않게
            if now - until > float(self.cfg["reset_opens_after_sec"]):
                h["opens"] = 0
            self._event(h, action="half_open", opens=h["opens"])
            self._save()
        return True, h["state"]

    def pause_remaining(self, host: str) -> float:
        """회로를 열기 전의 짧은 쉼(backoff)이 얼마나 남았는가. 다시 뜬 프로세스도 이만큼은 기다린다."""
        return max(0.0, float(self._host(host).get("pause_until") or 0.0) - self._now())

    def success(self, host: str) -> None:
        h = self._host(host)
        was = h["state"]
        dirty = was != "closed" or h["consecutive"] or h.get("pause_until")
        h.update(state="closed", consecutive=0, open_until=None, pause_until=None)
        h["successes"] = int(h.get("successes") or 0) + 1
        if h["opens"] and h["successes"] >= int(self.cfg["close_after_successes"]):
            h["opens"] = 0
            dirty = True
        if was != "closed":
            self._event(h, action="closed")
        if dirty:
            self._save()

    def failure(self, host: str, *, kind: str, status: int | None = None, retry_after: str | None = None,
                body: str | None = None, message: str | None = None) -> dict[str, Any]:
        """
        실패 하나를 기록하고 무엇을 해야 하는지 돌려준다.

            {"opened": True,  "open_until": iso, "cooldown_sec": n}   회로를 열었다 — 이 공급처에 더 보내지 않는다
            {"opened": False, "pause_sec": n}                          공급처 전체가 n초 쉰 뒤 같은 요청을 다시 보내도 된다
            {"opened": False, "pause_sec": None}                       이 breaker 가 다루지 않는 실패(404 등) — 호출자가 알아서 한다
        """
        if kind not in THROTTLE_KINDS and kind not in OUTAGE_KINDS:
            return {"opened": False, "pause_sec": None}
        h = self._host(host)
        now = self._now()
        asked = parse_retry_after(retry_after, now=now) if kind in THROTTLE_KINDS else None
        h["consecutive"] = int(h.get("consecutive") or 0) + 1
        h["successes"] = 0
        h["last_error"] = message or kind
        h["last_status"], h["last_retry_after"], h["last_body"] = status, retry_after, (body or "")[:120] or None
        # 쉬는 시간이 끝난 뒤의 시험 요청(half-open)은 half_open_failures 번까지 봐준다 — 요청의 절반쯤이 429 인 날에는
        # 시험 요청 하나가 우연히 막힌 것만으로 쉬는 시간이 2배가 되기 때문이다(2026-11-27)
        probing = h["state"] == "half_open" and h["consecutive"] >= int(self.cfg["half_open_failures"])
        # 공급처가 쉬라고 말했으면(Retry-After) 그 말을 따른다 — 임계를 기다리지 않고 바로 연다
        if asked is not None or probing or h["consecutive"] >= int(self.cfg["threshold"]):
            h["opens"] = int(h.get("opens") or 0) + 1
            if asked is not None:
                cooldown = min(max(asked, 1.0), float(self.cfg["retry_after_cap_sec"]))
                basis = "retry_after"
            else:
                cooldown = min(float(self.cfg["base_cooldown_sec"]) * (2 ** (h["opens"] - 1)), float(self.cfg["max_cooldown_sec"]))
                basis = "exponential_backoff"
            h.update(state="open", open_until=now + cooldown, pause_until=None)
            self._event(h, action="opened", kind=kind, status=status, retry_after=retry_after, body=(body or "")[:60] or None,
                        cooldown_sec=round(cooldown), basis=basis, opens=h["opens"])
            self._save()
            return {"opened": True, "open_until": _iso(h["open_until"]), "cooldown_sec": cooldown, "basis": basis}
        steps = [float(x) for x in (self.cfg["backoff_sec"] or [10.0])]
        pause = steps[min(h["consecutive"] - 1, len(steps) - 1)]
        h["pause_until"] = now + pause
        self._event(h, action="backoff", kind=kind, status=status, retry_after=retry_after, body=(body or "")[:60] or None, pause_sec=pause)
        self._save()
        return {"opened": False, "pause_sec": pause}

    # ── 보고 ──────────────────────────────────────────────
    def snapshot(self) -> dict[str, Any]:
        """호스트별 현재 상태(사람이 읽는 보고용). open 이면 언제 다시 시도할 수 있는지가 들어 있다."""
        now = self._now()
        out: dict[str, Any] = {}
        for host, h in self._doc["hosts"].items():
            until = h.get("open_until")
            state = h["state"]
            if state == "open" and until is not None and now >= float(until):
                state = "half_open"  # 쉬는 시간이 끝났다 — 다음 요청이 시험 요청이다
            out[host] = {"state": state, "consecutive_failures": h.get("consecutive", 0), "opens": h.get("opens", 0),
                         "open_until": _iso(until) if state == "open" else None,
                         "retry_in_sec": round(float(until) - now) if state == "open" and until else 0,
                         "last_status": h.get("last_status"), "last_retry_after": h.get("last_retry_after"),
                         "last_body": h.get("last_body"), "last_error": h.get("last_error")}
        return out

    def next_retry_at(self) -> str | None:
        """열려 있는 회로 가운데 가장 먼저 풀리는 시각. 열린 것이 없으면 None."""
        now = self._now()
        opens = [float(h["open_until"]) for h in self._doc["hosts"].values() if h["state"] == "open" and h.get("open_until") and float(h["open_until"]) > now]
        return _iso(min(opens)) if opens else None
