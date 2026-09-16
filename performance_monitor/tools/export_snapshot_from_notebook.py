"""기존 notebook 을 평소대로 실행한 뒤, 그 결과를 그대로 스냅샷으로 내보낸다.

**이 방식이 권장 경로다.** 계산을 다시 하지 않고 노트북이 만든 객체를 그대로 저장하므로
Dashboard 결과가 notebook 결과와 다를 수 없다.

사용법 (Performance_Analysis_Module_ver2_.ipynb 맨 아래 셀에서)::

    import sys
    sys.path.append('/path/to/performance_monitor')
    from tools.export_snapshot_from_notebook import export
    export(globals())

출력::

    data/processed/snapshot_20260911/
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# 프로젝트 루트를 경로에 넣는다 (폴더 이름에 의존하지 않는다).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config  # noqa: E402
from src.data_loader import SnapshotStore  # noqa: E402
from src.logging_utils import RunLog, get_logger  # noqa: E402

# export() 가 반드시 필요로 하는 notebook 변수 (계산 결과 + 파라미터)
REQUIRED_VARS = [
    "analysis_bm", "mp_end_date", "report_start_date", "mp_start_date",
    "return_contribution_final", "final_mp",
    "temp_return_final", "betalog_final",
]
# 있으면 더 많은 화면이 채워지는 변수
OPTIONAL_VARS = [
    "compare_final", "sector_compare_final", "new_sector_compare_final",
    "sector_index_market_cap", "new_sector_index_market_cap",
    "info_stock", "rtn_bpm", "alphalog_final",
    "list_bpm_factor", "list_bpm_sector", "bm_pre_rebal",
    "mtd_date", "qtd_date", "htd_date", "ytd_date", "y1_date",
]


def check(namespace: dict, show: bool = True) -> dict:
    """notebook 에 필요한 변수가 다 있는지 먼저 확인한다.

        pm.check_namespace(globals())

    ``export`` 는 **계산을 하지 않는다.** 노트북이 이미 만들어 둔 객체를 그대로
    저장할 뿐이므로, 주간 분석 노트북을 **같은 커널에서** 끝까지 돌린 뒤에
    호출해야 한다. 이 함수는 어디까지 돌았는지 보여 준다.
    """
    missing = [name for name in REQUIRED_VARS if name not in namespace]
    present = [name for name in REQUIRED_VARS if name in namespace]
    opt_present = [name for name in OPTIONAL_VARS if name in namespace]
    opt_missing = [name for name in OPTIONAL_VARS if name not in namespace]

    if show:
        if missing:
            print(f"✗ 필수 변수 {len(missing)}개가 없습니다: {', '.join(missing)}")
            print("  export_snapshot 은 계산을 하지 않습니다. 노트북이 만들어 둔")
            print("  결과를 저장할 뿐이므로, 주간 분석 노트북을 **같은 커널에서**")
            print("  끝까지 실행한 뒤 호출하십시오.")
            print("  화면만 먼저 보시려면: pm.demo_snapshot()  (합성 데이터)")
        else:
            print(f"✓ 필수 변수 {len(present)}개 모두 있습니다. "
                  "pm.export_snapshot(globals()) 을 실행하십시오.")
        if opt_missing:
            print(f"\n  선택 변수 {len(opt_present)}/{len(OPTIONAL_VARS)}개 있음. "
                  f"없는 것: {', '.join(opt_missing)}")
            print("  (없어도 되지만 일부 화면이 비거나 기간 프리셋이 줄어듭니다)")

    return {"missing": missing, "present": present,
            "optional_present": opt_present, "optional_missing": opt_missing,
            "ready": not missing}


# (스냅샷 테이블명, notebook 변수명, 필수여부)
EXPORT_MAP = [
    ("final_mp", "final_mp", True),
    ("temp_return_final", "temp_return_final", True),
    ("betalog_final", "betalog_final", True),
    ("return_contribution_final", "return_contribution_final", True),
    ("compare_final", "compare_final", False),
    ("sector_compare_final", "sector_compare_final", False),
    ("new_sector_compare_final", "new_sector_compare_final", False),
    ("sector_index_market_cap", "sector_index_market_cap", False),
    ("new_sector_index_market_cap", "new_sector_index_market_cap", False),
    ("info_stock", "info_stock", False),
    ("rtn_bpm", "rtn_bpm", False),
    ("alphalog_final", "alphalog_final", False),
]

# final_mp 는 매우 넓다(모델 × 항목 기여도 컬럼). 대시보드에 필요한 컬럼만 남긴다.
KEEP_PREFIXES = (
    "total_", "active_contribution_", "market_timing_contribution_",
    "country_contribution_", "specific_contribution_",
)
KEEP_COLUMNS = ("bm", "bm_next", "return_d", "forward_return_d",
                "q_sector", "new_sector", "predictive_beta", "specific_return")


def _select_final_mp_columns(final_mp: pd.DataFrame, columns, list_bpm,
                             slim: bool) -> pd.DataFrame:
    if not slim:
        return final_mp
    keep = set(KEEP_COLUMNS)
    for col in columns:
        keep.add(col)
        keep.add(col + "_next")
        keep.add("total_" + col)
        for prefix in ("active_contribution_", "market_timing_contribution_",
                       "country_contribution_", "specific_contribution_"):
            keep.add(prefix + col)
        # risk/industry factor 기여도는 항목별 화면(Attribution)에서 필요하다.
        for factor in list_bpm:
            keep.add(f"{factor}_contribution_{col}")
    keep.update(list_bpm)
    present = [c for c in final_mp.columns if c in keep]
    return final_mp[present]


def export(namespace: dict, config_dir: str | None = None,
           slim: bool = True, as_of: str | None = None) -> Path:
    """notebook 의 ``globals()`` 를 받아 스냅샷을 만든다."""
    config = load_config(config_dir)
    log = RunLog(get_logger(log_dir=config.log_dir))

    # 빠진 것이 있으면 첫 번째에서 죽지 말고 전부 모아서 알려 준다.
    absent = [name for name in REQUIRED_VARS if name not in namespace]
    if absent:
        raise KeyError(
            f"notebook 에 다음 변수가 없습니다: {', '.join(absent)}\n"
            "  export_snapshot 은 계산을 하지 않습니다. 노트북이 이미 만들어 둔\n"
            "  결과를 그대로 저장할 뿐이므로, 주간 분석 노트북을 **같은 커널에서**\n"
            "  끝까지 실행한 뒤 호출하십시오.\n"
            "    pm.check_namespace(globals())   # 어디까지 왔는지 확인\n"
            "    pm.demo_snapshot()              # 화면만 먼저 볼 때 (합성 데이터)"
        )

    def need(name: str):
        return namespace[name]

    analysis_bm = need("analysis_bm")
    mp_end_date = str(need("mp_end_date"))[:10]
    report_start_date = str(need("report_start_date"))[:10]
    mp_start_date = str(need("mp_start_date"))[:10]
    return_contribution_final = need("return_contribution_final")
    final_mp = need("final_mp")

    columns = list(return_contribution_final.columns)
    list_bpm_factor = list(namespace.get("list_bpm_factor", []))
    list_bpm_sector = list(namespace.get("list_bpm_sector", []))
    list_bpm = list_bpm_factor + list_bpm_sector

    as_of = as_of or mp_end_date
    manifest = {
        "as_of": as_of,
        "analysis_bm": analysis_bm,
        "mp_start_date": mp_start_date,
        "report_start_date": report_start_date,
        "mp_end_date": mp_end_date,
        "models": columns,
        "top_model_column": config.top_model_column(analysis_bm) if config.model_prefix(analysis_bm) else columns[-1],
        "list_bpm_factor": list_bpm_factor,
        "list_bpm_sector": list_bpm_sector,
        "bm_pre_rebal": bool(namespace.get("bm_pre_rebal", False)),
        "source": "notebook_export",
        "n_rows_final_mp": int(len(final_mp)),
    }

    store = SnapshotStore.create(config.processed_dir, as_of, manifest)
    log.info(f"스냅샷 생성 시작: {store.path}")

    for table_name, var_name, required in EXPORT_MAP:
        if var_name not in namespace:
            if required:
                raise KeyError(f"notebook 에 '{var_name}' 이 없습니다.")
            log.warning(f"{var_name} 없음 - 건너뜀")
            continue
        frame = namespace[var_name]
        if table_name == "final_mp":
            frame = _select_final_mp_columns(frame, columns, list_bpm, slim)
            log.info(f"final_mp 컬럼 {len(namespace[var_name].columns)} → {len(frame.columns)}")
        store.write_table(table_name, frame)
        log.info(f"저장 | {table_name} {getattr(frame, 'shape', '')}")

    # 비교기간 기준일
    anchors = {}
    for key, var in (("MTD", "mtd_date"), ("QTD", "qtd_date"), ("HTD", "htd_date"),
                     ("YTD", "ytd_date"), ("1Y", "y1_date")):
        if var in namespace and namespace[var] is not None:
            value = namespace[var]
            text = str(value)
            if len(text) == 8 and text.isdigit():
                text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
            anchors[key] = text[:10]
    anchors["WTD"] = report_start_date
    store.write_json("anchors", anchors)
    log.info(f"anchors: {anchors}")

    # 참고용 원본 파라미터
    store.write_json("notebook_params", {
        "mp_start_date": mp_start_date,
        "report_start_date": report_start_date,
        "mp_end_date": mp_end_date,
        "analysis_bm": analysis_bm,
        "bm_pre_rebal": bool(namespace.get("bm_pre_rebal", False)),
        "mp_list": list(namespace.get("mp_list", [])),
        "mp_nm": namespace.get("mp_nm"),
    })

    log.info(f"스냅샷 완료: {store.path}")
    return store.path


if __name__ == "__main__":  # pragma: no cover
    print(__doc__)
