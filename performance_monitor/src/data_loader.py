"""Data Layer.

두 가지 백엔드를 제공한다.

1. :class:`SnapshotStore` — 주 1회 생성된 스냅샷(parquet)을 읽는다.
   **Dashboard 는 이것만 사용한다.** 사내 라이브러리/DB/인터넷이 필요 없다.
2. :class:`DbSource` — 기존 notebook 과 동일하게 사내 DB(MSSQL/Tibero)와
   ``vrksa``/``jackhammer`` 를 호출한다. ``tools/build_snapshot.py`` 에서만 쓴다.
   import 는 모두 지연(lazy)이라 사내 라이브러리가 없는 환경에서도
   이 모듈을 import 하는 것 자체는 실패하지 않는다.

파일명을 코드에 하드코딩하지 않는다. 최신 스냅샷은
``manifest.json`` 의 ``as_of`` (동률이면 디렉터리 mtime) 로 자동 선택한다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import AppConfig, load_config

SNAPSHOT_PREFIX = "snapshot_"

# 스냅샷을 구성하는 테이블. (name, 필수여부)
SNAPSHOT_TABLES = [
    ("final_mp", True),
    ("temp_return_final", True),
    ("betalog_final", True),
    ("return_contribution_final", True),
    ("compare_final", False),
    ("sector_compare_final", False),
    ("new_sector_compare_final", False),
    ("sector_index_market_cap", False),
    ("new_sector_index_market_cap", False),
    ("info_stock", False),
    ("rtn_bpm", False),
]


# ---------------------------------------------------------------------------
# Snapshot 탐색
# ---------------------------------------------------------------------------
@dataclass
class SnapshotInfo:
    path: Path
    manifest: dict

    @property
    def as_of(self) -> str:
        return self.manifest.get("as_of", self.path.name.replace(SNAPSHOT_PREFIX, ""))

    @property
    def benchmark(self) -> str:
        return self.manifest.get("analysis_bm", "")

    @property
    def created_at(self) -> str:
        return self.manifest.get("created_at", "")

    @property
    def cache_key(self) -> tuple:
        """파일이 바뀌면 캐시가 무효화되도록 (경로, mtime, size) 튜플을 만든다."""
        parts = [str(self.path)]
        for item in sorted(self.path.glob("*")):
            stat = item.stat()
            parts.append(f"{item.name}:{stat.st_mtime_ns}:{stat.st_size}")
        return tuple(parts)


def list_snapshots(config: AppConfig | None = None) -> list[SnapshotInfo]:
    """processed 디렉터리의 스냅샷을 최신순으로 반환."""
    config = config or load_config()
    root = config.processed_dir
    if not root.exists():
        return []
    found = []
    for directory in root.iterdir():
        if not directory.is_dir():
            continue
        manifest_path = directory / "manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = {}
        found.append(SnapshotInfo(path=directory, manifest=manifest))
    found.sort(key=lambda s: (s.as_of, s.path.stat().st_mtime), reverse=True)
    return found


def latest_snapshot(config: AppConfig | None = None,
                    benchmark: str | None = None) -> SnapshotInfo | None:
    for snapshot in list_snapshots(config):
        if benchmark is None or snapshot.benchmark == benchmark:
            return snapshot
    return None


# ---------------------------------------------------------------------------
# SnapshotStore
# ---------------------------------------------------------------------------
class SnapshotStore:
    """스냅샷 디렉터리 읽기/쓰기."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    # -- write ------------------------------------------------------------
    @classmethod
    def create(cls, processed_dir: Path, as_of: str, manifest: dict) -> "SnapshotStore":
        directory = Path(processed_dir) / f"{SNAPSHOT_PREFIX}{as_of.replace('-', '')}"
        directory.mkdir(parents=True, exist_ok=True)
        store = cls(directory)
        store.write_manifest(manifest)
        return store

    def write_manifest(self, manifest: dict) -> None:
        payload = dict(manifest)
        payload.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
        (self.path / "manifest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def write_table(self, name: str, frame: pd.DataFrame) -> None:
        """parquet 로 저장. 실패 시 pickle 로 폴백한다.

        `return_contribution_final` 처럼 object dtype 이 섞인 표는
        parquet 이 거부할 수 있어 폴백이 필요하다.
        """
        target = self.path / f"{name}.parquet"
        try:
            frame.to_parquet(target)
            return
        except Exception:  # noqa: BLE001 - pyarrow 미설치/타입 문제 모두 폴백
            if target.exists():
                target.unlink()
        frame.to_pickle(self.path / f"{name}.pkl")

    def write_json(self, name: str, payload: dict) -> None:
        (self.path / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    # -- read -------------------------------------------------------------
    @property
    def manifest(self) -> dict:
        path = self.path / "manifest.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def has(self, name: str) -> bool:
        return (self.path / f"{name}.parquet").exists() or (self.path / f"{name}.pkl").exists()

    def read_table(self, name: str) -> pd.DataFrame | None:
        parquet = self.path / f"{name}.parquet"
        if parquet.exists():
            return pd.read_parquet(parquet)
        pickle_path = self.path / f"{name}.pkl"
        if pickle_path.exists():
            return pd.read_pickle(pickle_path)
        return None

    def read_json(self, name: str) -> dict:
        path = self.path / f"{name}.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def load_all(self) -> dict:
        """스냅샷 전체를 dict 로 로드."""
        bundle = {"manifest": self.manifest, "anchors": self.read_json("anchors")}
        for name, required in SNAPSHOT_TABLES:
            frame = self.read_table(name)
            if frame is None and required:
                raise FileNotFoundError(
                    f"스냅샷에 필수 테이블이 없습니다: {name} ({self.path})"
                )
            bundle[name] = frame
        return normalize_bundle(bundle)


def normalize_bundle(bundle: dict) -> dict:
    """저장/복원 과정에서 흐트러질 수 있는 index 타입을 되돌린다."""
    for key in ("final_mp",):
        frame = bundle.get(key)
        if frame is not None and isinstance(frame.index, pd.MultiIndex):
            frame.index = frame.index.set_names(["date", "item"])
    for key in ("temp_return_final", "betalog_final"):
        frame = bundle.get(key)
        if frame is not None and not isinstance(frame.index, pd.DatetimeIndex):
            frame.index = pd.to_datetime(frame.index, utc=True)
    return bundle


# ---------------------------------------------------------------------------
# 데이터 상태 요약 (화면 상단 표기용)
# ---------------------------------------------------------------------------
def data_status(bundle: dict) -> dict:
    """'Data As of / Portfolio Data / Price Data / ...' 표기용 요약."""
    manifest = bundle.get("manifest", {})
    final_mp = bundle.get("final_mp")
    status = {
        "data_as_of": manifest.get("as_of", "-"),
        "benchmark": manifest.get("analysis_bm", "-"),
        "period": f"{manifest.get('report_start_date','-')} ~ {manifest.get('mp_end_date','-')}",
        "created_at": manifest.get("created_at", "-"),
        "source": manifest.get("source", "-"),
    }
    checks = {}
    checks["Portfolio Data"] = final_mp is not None and len(final_mp) > 0
    checks["Price Data"] = final_mp is not None and "return_d" in getattr(final_mp, "columns", [])
    checks["Benchmark Data"] = (
        bundle.get("temp_return_final") is not None
        and "bm" in bundle["temp_return_final"].columns
    )
    checks["Model Data"] = bundle.get("return_contribution_final") is not None
    checks["Attribution Data"] = bundle.get("compare_final") is not None
    status["checks"] = {k: ("정상" if v else "없음") for k, v in checks.items()}

    missing = 0
    if final_mp is not None and "return_d" in final_mp.columns:
        missing = int(final_mp["return_d"].isna().sum())
    status["missing_data"] = missing
    status["n_stocks"] = (
        int(final_mp.index.get_level_values("item").nunique()) if final_mp is not None else 0
    )
    return status


# ---------------------------------------------------------------------------
# DbSource - 기존 notebook 과 동일한 사내 데이터 접근
# ---------------------------------------------------------------------------
class DbSource:
    """사내 DB / vrksa / jackhammer 접근 래퍼.

    **이 클래스는 스냅샷 생성 시에만 사용한다.** 대시보드 실행 경로에는 없다.
    모든 SQL 문자열은 기존 notebook / shared_data.py 의 것을 그대로 사용한다.
    """

    def __init__(self, config: AppConfig | None = None):
        self.config = config or load_config()
        self._conn = None
        self._conn2 = None

    # -- connections ------------------------------------------------------
    @property
    def conn(self):
        """MSSQL (BQUANT). 원본: ``create_engine('mssql+pymssql://...').connect()``"""
        if self._conn is None:
            from sqlalchemy import create_engine

            self._conn = create_engine(self.config.mssql_url).connect()
        return self._conn

    @property
    def conn2(self):
        """Tibero (PBIDB). 원본: ``pyodbc.connect(conn_str)`` + 인코딩 설정"""
        if self._conn2 is None:
            import pyodbc

            conn = pyodbc.connect(self.config.tibero_dsn)
            conn.setdecoding(pyodbc.SQL_CHAR, encoding=self.config.raw["database"]["tibero_char_encoding"])
            conn.setdecoding(pyodbc.SQL_WCHAR, encoding="utf-8")
            conn.setdecoding(pyodbc.SQL_WMETADATA, encoding="utf-32le")
            conn.setencoding(encoding="utf-8")
            self._conn2 = conn
        return self._conn2

    def close(self) -> None:
        for conn in (self._conn, self._conn2):
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
        self._conn = self._conn2 = None

    # -- target weights (shared_data.load_target_weights 와 동일) ----------
    def load_target_weights(self, pid: str, target_date: str = "all") -> pd.DataFrame:
        """원본: ``shared_data.load_target_weights``"""
        if target_date == "all":
            query = (
                "select * from portfolios.simple_rebalancing_target_weights "
                f"where portfolio_id = '{pid}'"
            )
        else:
            query = (
                "select * from portfolios.simple_rebalancing_target_weights "
                f"where portfolio_id = '{pid}' and date='{target_date}'"
            )
        result = self.conn.execute(query)
        frame = pd.DataFrame(result.fetchall())
        if frame.empty:
            return frame
        frame.columns = result.keys()
        frame = frame[["date", "asset", "weight"]]
        frame["date"] = pd.to_datetime(frame["date"], utc=True)
        frame = frame.rename(columns={"asset": "item"}).set_index(["date", "item"])
        return frame

    def load_info_stock(self) -> pd.DataFrame:
        """원본 (contrib CELL 5)::

            q_info_stock = "SELECT gicode item, itemabbrnm name_stock FROM FNGDB.dbo.fns_j_mast"
        """
        query = "SELECT gicode item, itemabbrnm name_stock FROM FNGDB.dbo.fns_j_mast "
        return pd.read_sql(query, self.conn, columns=True, index_col="item")

    def load_period_anchors(self, mp_end_date: str) -> dict:
        """비교기간 기준일.

        원본 (Performance_Analysis_Module CELL 16~18) 의 SQL 을 그대로 사용한다.
        """
        end = mp_end_date.replace("-", "")
        query = f'''SELECT  "date"           AS TD
                , (SELECT  MAX("date") FROM AQUANT.dbo.WORKDATE_MAST_TB WHERE "date" < '{end}' AND "W_E" = '1' AND "SYSTEM_GUBUN" = 'T')
                                    AS WTD
                , (SELECT  MAX("date") FROM AQUANT.dbo.WORKDATE_MAST_TB WHERE "date" < '{end}' AND "M_E" = '1' AND "SYSTEM_GUBUN" = 'T')
                                    AS MTD
                , (SELECT MAX("date")  FROM AQUANT.dbo.WORKDATE_MAST_TB WHERE "date" <= '{end}' AND "M_E" = '1' AND "SYSTEM_GUBUN" = 'T' AND SUBSTRING("date", 5, 2) IN ('03', '06', '09', '12'))
                                    AS QTD
                , (SELECT MAX("date")  FROM AQUANT.dbo.WORKDATE_MAST_TB WHERE "date" <= '{end}' AND "M_E" = '1' AND "SYSTEM_GUBUN" = 'T' AND SUBSTRING("date", 5, 2) IN ( '06', '12'))
                                    AS HTD
                , (SELECT  MAX("date") FROM AQUANT.dbo.WORKDATE_MAST_TB WHERE "date" < '{end}' AND "Y_E" = '1' AND "SYSTEM_GUBUN" = 'T')
                                    AS YTD
                                    ,  "DATE_1y_ago"    AS '1y_ago'

             FROM  AQUANT.dbo.WORKDATE_MAST_TB

            WHERE "date"         = '{end}'
              AND "SYSTEM_GUBUN" = 'T'

           ORDER BY 1 DESC'''
        frame = pd.read_sql(query, self.conn, columns=True)
        if frame.empty:
            return {}

        def _fmt(value):
            if value is None:
                return None
            text = str(value)
            return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if len(text) == 8 else text

        return {
            "MTD": _fmt(frame["MTD"][0]),
            "QTD": _fmt(frame["QTD"][0]),
            "HTD": _fmt(frame["HTD"][0]),
            "YTD": _fmt(frame["YTD"][0]),
            "1Y": _fmt(frame["1y_ago"][0]),
        }
