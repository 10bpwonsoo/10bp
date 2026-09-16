"""설정 파일 로딩.

모델명 / Benchmark / 섹터 수기조정 / CA 는 코드가 아니라 config 에서 읽는다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_DIR = PACKAGE_ROOT / "config"


@dataclass
class AppConfig:
    raw: dict
    config_dir: Path
    root: Path

    # --- paths -------------------------------------------------------------
    @property
    def data_dir(self) -> Path:
        """데이터 루트.

        환경변수 ``PM_DATA_DIR`` 이 우선한다. 프로그램은 로컬 디스크에 두고
        스냅샷만 공유 폴더(네트워크 드라이브)에 둘 때 쓴다 —
        Streamlit 은 프로그램이 네트워크 경로에 있으면 실행을 거부하지만,
        데이터를 네트워크에서 읽는 것은 문제되지 않는다.

            set PM_DATA_DIR=M:/공유폴더/performance_monitor_data
        """
        override = os.environ.get("PM_DATA_DIR")
        if override:
            return Path(override)
        return self._resolve(self.raw["project"]["data_dir"])

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / self.raw["project"]["processed_subdir"]

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / self.raw["project"]["raw_subdir"]

    @property
    def archive_dir(self) -> Path:
        return self.data_dir / self.raw["project"]["archive_subdir"]

    @property
    def reference_dir(self) -> Path:
        return self.data_dir / self.raw["project"]["reference_subdir"]

    @property
    def log_dir(self) -> Path:
        return self._resolve(self.raw["project"]["log_dir"])

    def _resolve(self, value) -> Path:
        path = Path(value)
        return path if path.is_absolute() else (self.root / path)

    # --- benchmarks --------------------------------------------------------
    @property
    def benchmarks(self) -> dict:
        return self.raw["benchmarks"]

    @property
    def default_benchmark(self) -> str:
        return self.raw.get("default_benchmark", "kospi200")

    def benchmark(self, key: str) -> dict:
        return self.raw["benchmarks"][key]

    def benchmark_display(self, key: str) -> str:
        return self.raw["benchmarks"].get(key, {}).get("display_name", key)

    # --- models ------------------------------------------------------------
    def model_prefix(self, benchmark_key: str):
        return self.raw["benchmarks"].get(benchmark_key, {}).get("model_prefix")

    def model_group(self, benchmark_key: str) -> dict:
        prefix = self.model_prefix(benchmark_key)
        if prefix is None:
            return {}
        return self.raw.get("models", {}).get(prefix, {})

    def model_display_names(self, benchmark_key: str) -> dict:
        """DB portfolio_id / 컬럼명 -> 화면 표시명."""
        group = self.model_group(benchmark_key)
        if not group:
            return {}
        mapping = {
            group["top_model_column"]: group.get("top_model_display", group["top_model_column"]),
            group["top_model_id"]: group.get("top_model_display", group["top_model_id"]),
        }
        for sub in group.get("sub_models", []):
            mapping[sub["id"]] = sub.get("display_name", sub["id"])
        return mapping

    def mp_list(self, benchmark_key: str) -> list:
        """원본 notebook 의 ``mp_list`` 와 동일한 순서."""
        group = self.model_group(benchmark_key)
        return [sub["id"] for sub in group.get("sub_models", [])]

    def top_model_column(self, benchmark_key: str) -> str:
        return self.model_group(benchmark_key).get("top_model_column", "RP")

    def top_model_id(self, benchmark_key: str):
        return self.model_group(benchmark_key).get("top_model_id")

    # --- misc --------------------------------------------------------------
    @property
    def attribution(self) -> dict:
        return self.raw["attribution"]

    @property
    def periods(self) -> list:
        return self.raw["periods"]

    @property
    def optional_metrics(self) -> dict:
        return self.raw.get("optional_metrics", {})

    @property
    def validation(self) -> dict:
        return self.raw.get("validation", {})

    @property
    def ui(self) -> dict:
        return self.raw.get("ui", {})

    @property
    def mssql_url(self) -> str:
        db = self.raw["database"]
        return os.environ.get(db["mssql_url_env"], db["mssql_url_default"])

    @property
    def tibero_dsn(self) -> str:
        db = self.raw["database"]
        return os.environ.get(db["tibero_dsn_env"], db["tibero_dsn_default"])

    # --- side config files -------------------------------------------------
    @property
    def sector_overrides(self) -> dict:
        return _load_yaml(self.config_dir / "sector_overrides.yaml").get(
            "sector_overrides", {}
        )

    @property
    def corporate_actions(self) -> dict:
        return _load_yaml(self.config_dir / "corporate_actions.yaml")

    @property
    def bpm_factor_name_match(self) -> dict:
        return _load_yaml(self.config_dir / "bpm_factors.yaml").get(
            "bpm_factor_name_match", {}
        )

    @property
    def list_bpm_factor(self) -> list:
        return _load_yaml(self.config_dir / "bpm_factors.yaml").get(
            "list_bpm_factor", []
        )


def _load_yaml(path: Path) -> dict:
    if not Path(path).exists():
        return {}
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@lru_cache(maxsize=4)
def load_config(config_dir: str | None = None) -> AppConfig:
    directory = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
    raw = _load_yaml(directory / "config.yaml")
    if not raw:
        raise FileNotFoundError(f"config.yaml 을 찾을 수 없습니다: {directory}")
    return AppConfig(raw=raw, config_dir=directory, root=directory.parent)
