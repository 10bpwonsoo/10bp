"""FastAPI 앱. `uvicorn marketpulse.api.main:app --reload` 로 띄운다."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config.settings import get_settings
from .routes import graph, health, news, signals, snapshot, stream

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description=(
            "뉴스 내러티브와 마켓데이터를 결합한 시장 인텔리전스 API. "
            "모든 점수는 계산 근거(ScoreBreakdown)를 함께 돌려준다."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(snapshot.router)
    app.include_router(health.router)
    app.include_router(news.router)
    app.include_router(signals.router)
    app.include_router(graph.router)
    app.include_router(stream.router)
    return app


app = create_app()
