"""Notebook 에서 Dashboard 와 **동일한** Analytics Engine 을 쓰기 위한 shim.

기존 노트북을 그대로 두면서, 필요한 셀에서만 아래처럼 쓰면 된다::

    import pm_engine as pm

    # 0) 노트북에서 대시보드 보기 - 둘 중 편한 쪽
    pm.launch_dashboard()   # 서버를 띄운다 → http://<이 서버>:8501
    pm.report()             # 노트북 셀 안에 바로 그린다 (포트 못 열 때)

    # 1) 계산 (기존 notebook 변수를 그대로 넘긴다)
    Alog, alphalog, betalog = pm.performance.build_scaling_factors(
        temp_return_final, return_contribution_final, report_date_list)

    # 2) 노트북 결과를 Dashboard 스냅샷으로 내보내기
    pm.export_snapshot(globals())

    # 3) 노트북 결과 vs 엔진 결과 대조 (PHASE 10)
    pm.compare(globals())

이렇게 하면 계산식이 한 곳(`performance_monitor/src/`)에만 존재하게 되어
앞으로 로직을 고칠 때 Notebook 과 Dashboard 가 갈라지지 않는다.

                 performance_monitor/src  (Core Analytics)
                            ↑
                   ┌────────┴────────┐
                Notebook          Dashboard
"""
from __future__ import annotations

import sys
from pathlib import Path

# performance_monitor 패키지 루트를 sys.path 에 추가
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
for _path in (str(_REPO_ROOT), str(_PACKAGE_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from src import (  # noqa: E402,F401
    attribution,
    benchmark,
    config,
    dashboard_engine,
    data_loader,
    model_analysis,
    performance,
    pipeline,
    portfolio,
    utils,
    validation,
)

from src.launcher import (  # noqa: E402,F401
    dashboard_status,
    launch_dashboard,
    stop_dashboard,
)

__all__ = [
    "attribution", "benchmark", "config", "dashboard_engine", "data_loader",
    "model_analysis", "performance", "pipeline", "portfolio", "utils", "validation",
    "export_snapshot", "compare", "run_attribution", "load_config",
    "launch_dashboard", "stop_dashboard", "dashboard_status",
    "report", "snapshots",
]

run_attribution = pipeline.run_attribution
load_config = config.load_config


def report(*args, **kwargs):
    """노트북 셀 안에 대시보드 요약 화면을 그린다.

        pm.report()                      # 최신 스냅샷 / 상위 모델 / 주간
        pm.report(preset='MTD')          # 월간
        pm.report(model='KS2_VALUE_FP')  # 특정 하위 모델

    Dashboard 와 **같은 엔진**으로 계산하므로 숫자가 같다.
    """
    from src.notebook_report import report as _report

    return _report(*args, **kwargs)


def snapshots():
    """쓸 수 있는 스냅샷 목록."""
    from src.notebook_report import available_snapshots

    return available_snapshots()


def export_snapshot(namespace: dict, **kwargs):
    """현재 notebook 결과를 Dashboard 스냅샷으로 저장한다.

        pm.export_snapshot(globals())
    """
    from tools.export_snapshot_from_notebook import export

    return export(namespace, **kwargs)


def compare(namespace: dict, **kwargs):
    """notebook 결과 vs Analytics Engine 결과 대조표를 출력한다.

        pm.compare(globals())
    """
    from tools.compare_with_notebook import compare as _compare

    return _compare(namespace, **kwargs)
