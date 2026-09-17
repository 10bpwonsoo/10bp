r"""Notebook 에서 Dashboard 와 **동일한** Analytics Engine 을 쓰기 위한 shim.

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

    # 4) 코드 업데이트 (data/ 는 건드리지 않는다)
    pm.check_github()                       # 사내망에서 GitHub 가 열리는지 확인
    pm.update()                             # 열리면 GitHub 에서
    pm.update(r'C:\temp\performance_monitor_win.zip')   # 막혀 있으면 반입 파일로

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
    detect_jupyter_proxy,
    launch_dashboard,
    stop_dashboard,
)

from src.updater import (  # noqa: E402,F401
    check_github,
    current_version,
    update,
    update_from_file,
    update_from_github,
)

__all__ = [
    "attribution", "benchmark", "config", "dashboard_engine", "data_loader",
    "model_analysis", "performance", "pipeline", "portfolio", "utils", "validation",
    "export_snapshot", "compare", "run_attribution", "load_config",
    "launch_dashboard", "stop_dashboard", "dashboard_status", "jupyter_proxy",
    "report", "snapshots", "check_namespace", "demo_snapshot", "export_html", "publish",
    "check_github", "update", "update_from_github", "update_from_file",
    "current_version",
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


def export_html(*args, **kwargs):
    """리포트를 HTML 파일 하나로 내보낸다 (휴대폰·사외 열람용).

        pm.export_html()                # 주간
        pm.export_html(preset='MTD')    # 월간
        pm.export_html(slim=True)       # 파일 작게 (볼 때 인터넷 필요)

    서버를 노출하지 않고 **파일 하나**로 만들어 승인된 사내 채널로 보낸다.
    내부용·대외비 표시가 들어간다. 계산은 Dashboard 와 같은 엔진을 쓴다.
    """
    from src.report_html import export_html as _export_html

    return _export_html(*args, **kwargs)


def publish(*args, **kwargs):
    """리포트를 Jupyter 주소로 열 수 있는 곳에 올린다.

        pm.publish()                 # 주간
        pm.publish(preset='MTD')     # 월간

    새 포트도, jupyter-server-proxy 도 필요 없다. 지금 쓰는 Jupyter 포트를
    그대로 쓰므로 사내에서 바로 열리고, VPN 붙은 휴대폰에서도 같은 주소로 열린다.
    """
    from src.report_html import publish as _publish

    return _publish(*args, **kwargs)


def jupyter_proxy(port: int = 8501):
    """Jupyter 주소를 통해 대시보드에 접속할 수 있는지 확인한다.

        pm.jupyter_proxy()

    사내에서 8501 같은 포트가 막혀 있을 때, jupyter-server-proxy 가 있으면
    **이미 열려 있는 Jupyter 포트**로 대시보드에 들어갈 수 있다.
    """
    return detect_jupyter_proxy(port, verbose=True)


def check_namespace(namespace: dict, **kwargs):
    """스냅샷을 만들 준비가 됐는지 먼저 확인한다.

        pm.check_namespace(globals())

    `export_snapshot` 은 계산을 하지 않는다. 노트북이 이미 만들어 둔 결과를
    저장할 뿐이므로, 주간 분석 노트북을 **같은 커널에서** 끝까지 돌려야 한다.
    이 함수는 어느 변수가 있고 없는지 보여 준다.
    """
    from tools.export_snapshot_from_notebook import check

    return check(namespace, **kwargs)


def demo_snapshot(weeks: int = 26, stocks: int = 120, report_days: int = 5,
                  seed: int = 20260911):
    """합성 데이터로 스냅샷을 만든다. **점검용이며 실제 운용 성과가 아니다.**

        pm.demo_snapshot(); pm.report()

    실제 데이터 없이 화면·설치가 제대로 됐는지 확인할 때만 쓴다.
    화면 상단에 데모 데이터라는 경고가 항상 표시된다.
    """
    from tools.make_demo_snapshot import main as _demo

    return _demo(weeks, stocks, report_days, seed)


def compare(namespace: dict, **kwargs):
    """notebook 결과 vs Analytics Engine 결과 대조표를 출력한다.

        pm.compare(globals())
    """
    from tools.compare_with_notebook import compare as _compare

    return _compare(namespace, **kwargs)
