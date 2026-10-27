"""
WebSocket 스트림 (설계서 STEP 6.5).

프론트는 5초 폴링으로도 동작한다. 이 경로는 그것을 **대체하지 않고**
보탠다 — 소켓이 끊겨도 폴링이 화면을 유지한다. 스트림 하나가 죽었다고
대시보드가 멈추면 안 된다.

보내는 것은 전체 스냅샷이 아니라 **바뀐 것**이다. 47종목 × 13테마 전체를
매 틱 밀면 대역폭도 낭비고 프론트가 매번 전면 재렌더한다. 다만 첫
메시지는 전체를 보낸다 — 붙자마자 화면이 채워져야 한다.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from ...models.snapshot import IntelligenceSnapshot
from ..deps import load_snapshot, resolve_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["stream"])

#: 서버가 다시 계산해 보는 주기. 캐시 TTL 보다 짧을 이유가 없다.
POLL_SEC = 5.0
#: 아무 변화가 없어도 이 주기로는 보낸다. 중간 장비가 유휴 연결을
#: 끊는 것을 막고, 프론트가 "살아 있음" 을 안다.
HEARTBEAT_SEC = 30.0


def digest(snapshot: IntelligenceSnapshot) -> str:
    """무엇이 바뀌었는지 가릴 지문. 같은 틱을 두 번 보내지 않는다."""
    return "|".join(
        [
            snapshot.as_of.isoformat(),
            snapshot.market_state.primary_label.value,
            f"{snapshot.market_state.confidence:.4f}",
            str(len(snapshot.divergences)),
            str(len([a for a in snapshot.alerts if a.state != "RESOLVED"])),
            f"{snapshot.data_health.coverage:.4f}",
        ]
    )


def delta(snapshot: IntelligenceSnapshot) -> dict:
    """전체 스냅샷 대신 화면 상단이 쓰는 것만."""
    state = snapshot.market_state
    return {
        "type": "delta",
        "as_of": snapshot.as_of.isoformat(),
        "market_state": {
            "label": state.primary_label.value,
            "label_ko": state.primary_label_ko,
            "confidence": state.confidence,
            "narrative": state.narrative,
            "narrative_source": state.narrative_source,
        },
        "counts": {
            "divergences": len(snapshot.divergences),
            "alerts_open": len([a for a in snapshot.alerts if a.state != "RESOLVED"]),
            "events": len(snapshot.events),
        },
        "coverage": snapshot.data_health.coverage,
        "mode": snapshot.data_health.mode.value,
        "warnings": snapshot.data_health.warnings[:3],
    }


@router.websocket("/stream")
async def stream(websocket: WebSocket, scenario: str | None = Query(default=None)) -> None:
    await websocket.accept()
    try:
        settings = resolve_settings(scenario)
    except HTTPException as exc:
        # 잘못된 시나리오는 즉시 알리고 닫는다. 조용히 기본값으로 돌지 않는다.
        await websocket.send_json({"type": "error", "detail": exc.detail})
        await websocket.close(code=1008)
        return

    last: str | None = None
    idle = 0.0

    try:
        while True:
            # 스냅샷 생성은 동기 코드다. 이벤트 루프를 막지 않게 스레드로 뺀다.
            snapshot = await asyncio.to_thread(load_snapshot, settings)
            fingerprint = digest(snapshot)

            if last is None:
                await websocket.send_json(
                    {"type": "snapshot", "snapshot": snapshot.model_dump(mode="json")}
                )
                last, idle = fingerprint, 0.0
            elif fingerprint != last:
                await websocket.send_json(delta(snapshot))
                last, idle = fingerprint, 0.0
            elif idle >= HEARTBEAT_SEC:
                await websocket.send_json({"type": "heartbeat", "as_of": snapshot.as_of.isoformat()})
                idle = 0.0

            await asyncio.sleep(POLL_SEC)
            idle += POLL_SEC
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001 — 소켓 하나가 서버를 흔들면 안 된다
        logger.exception("스트림 중단")
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass
