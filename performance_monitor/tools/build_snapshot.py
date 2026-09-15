"""주간 스냅샷 생성 (배치용).

**기존 notebook 을 그대로 실행한다.** 계산 로직을 재구현하지 않으므로
결과가 노트북과 다를 수 없다.

동작:
 1. ``Function_calculation_return_contribution_ver2.ipynb`` 의 **code 셀만** 순서대로 실행
    (IPython 의 ``%run notebook.ipynb`` 과 동일하게 raw/markdown 셀은 건너뛴다)
 2. 실행 전에 노트북이 기대하는 파라미터를 namespace 에 주입한다
    (원본 CELL 1 이 raw 셀이라 값이 외부에서 주어지는 구조 그대로다)
 3. 끝나면 ``export_snapshot_from_notebook.export(namespace)`` 로 스냅샷 저장

즉 사내 라이브러리(``jackhammer``, ``vrksa``)와 DB 접속이 **필요하다**.
Dashboard 실행에는 필요 없다.

사용법::

    python tools/build_snapshot.py \
        --mp-end-date 2026-09-11 \
        --report-start-date 2026-09-04 \
        --benchmark kospi200

    # 주간 배치 (매주 금요일 18:10)
    # 10 18 * * 5  cd /srv/performance_monitor && python tools/build_snapshot.py --auto

``--auto`` 는 오늘을 기준으로 ``mp_end_date`` = 직전 영업일,
``report_start_date`` = 그 전주 마지막 영업일로 잡는다 (DB 의 WORKDATE_MAST_TB 사용).
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

from performance_monitor.src.config import load_config  # noqa: E402
from performance_monitor.src.logging_utils import RunLog, get_logger  # noqa: E402
from performance_monitor.tools.export_snapshot_from_notebook import export  # noqa: E402

CONTRIB_NOTEBOOK = "Function_calculation_return_contribution_ver2.ipynb"


# ---------------------------------------------------------------------------
# notebook 실행
# ---------------------------------------------------------------------------
def _noop_display(*args, **kwargs):
    """노트북의 ``display()`` 호출을 배치 환경에서 무해하게 만든다."""
    return None


def run_notebook(path: Path, namespace: dict, log: RunLog) -> dict:
    """.ipynb 의 code 셀을 순서대로 exec 한다 (``%run`` 과 동일한 범위)."""
    notebook = json.loads(Path(path).read_text(encoding="utf-8"))
    namespace.setdefault("display", _noop_display)
    namespace.setdefault("__name__", "__main__")
    namespace.setdefault("__file__", str(path))

    executed = 0
    for position, cell in enumerate(notebook["cells"]):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell["source"])
        if not source.strip():
            continue
        if any(line.lstrip().startswith(("%", "!")) for line in source.splitlines()):
            log.warning(f"CELL {position}: IPython 매직/셸 명령이 있어 건너뜁니다.")
            continue
        try:
            exec(compile(source, f"<{path.name}:cell{position}>", "exec"), namespace)
            executed += 1
        except Exception:
            log.error(f"CELL {position} 실행 실패:\n{traceback.format_exc()}")
            raise
    log.info(f"{path.name}: code 셀 {executed}개 실행 완료")
    return namespace


# ---------------------------------------------------------------------------
# 파라미터
# ---------------------------------------------------------------------------
def resolve_auto_dates(config, log: RunLog) -> tuple[str, str]:
    """DB 에서 직전 영업일 / 전주 마지막 영업일을 구한다.

    원본 Performance_Analysis_Module CELL 16 의 WORKDATE_MAST_TB 규칙과 동일하다.
    """
    from performance_monitor.src.data_loader import DbSource

    source = DbSource(config)
    today = pd.Timestamp.today().strftime("%Y%m%d")
    query = f'''SELECT MAX("date") AS LAST_BD
                FROM AQUANT.dbo.WORKDATE_MAST_TB
                WHERE "date" <= '{today}' AND "SYSTEM_GUBUN" = 'T' '''
    frame = pd.read_sql(query, source.conn, columns=True)
    raw = str(frame["LAST_BD"][0])
    mp_end_date = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"

    anchors = source.load_period_anchors(mp_end_date)
    report_start_date = anchors.get("WTD")
    if report_start_date is None:
        query = f'''SELECT MAX("date") AS WTD
                    FROM AQUANT.dbo.WORKDATE_MAST_TB
                    WHERE "date" < '{raw}' AND "W_E" = '1' AND "SYSTEM_GUBUN" = 'T' '''
        wtd = str(pd.read_sql(query, source.conn, columns=True)["WTD"][0])
        report_start_date = f"{wtd[:4]}-{wtd[4:6]}-{wtd[6:8]}"
    source.close()
    log.info(f"--auto 로 결정: mp_end_date={mp_end_date}, report_start_date={report_start_date}")
    return mp_end_date, report_start_date


def main(args) -> int:
    config = load_config()
    log = RunLog(get_logger("build_snapshot", log_dir=config.log_dir))
    log.info("=" * 60)
    log.info("주간 스냅샷 생성 시작")

    notebook_dir = Path(args.notebook_dir) if args.notebook_dir else (ROOT / "notebooks")
    notebook_path = notebook_dir / CONTRIB_NOTEBOOK
    if not notebook_path.exists():
        log.error(f"노트북을 찾을 수 없습니다: {notebook_path}")
        return 2

    if args.auto:
        try:
            mp_end_date, report_start_date = resolve_auto_dates(config, log)
        except Exception as exc:  # noqa: BLE001
            log.error(f"--auto 날짜 조회 실패: {exc}")
            return 2
    else:
        mp_end_date = args.mp_end_date
        report_start_date = args.report_start_date
        if not (mp_end_date and report_start_date):
            log.error("--mp-end-date 와 --report-start-date 를 지정하거나 --auto 를 쓰십시오.")
            return 2

    # 원본 CELL 1(raw) 이 담당하던 파라미터를 그대로 주입한다.
    namespace: dict = {
        "mp_start_date": args.mp_start_date,
        "report_start_date": report_start_date,
        "mp_end_date": mp_end_date,
        "analysis_bm": args.benchmark,
        "data_load": True,
        "bm_pre_rebal": args.bm_pre_rebal,
    }
    if args.bm_pre_rebal:
        if not (args.rebal_end_dt and args.bm_reb_date):
            log.error("--bm-pre-rebal 사용 시 --rebal-end-dt 와 --bm-reb-date 가 필요합니다.")
            return 2
        namespace["rebal_end_dt"] = args.rebal_end_dt
        namespace["bm_reb_date"] = args.bm_reb_date

    log.info(f"파라미터 {json.dumps({k: v for k, v in namespace.items()}, ensure_ascii=False)}")
    log.info(f"노트북 실행: {notebook_path}")

    # 노트북은 자기 디렉터리 기준으로 shared_data / shared_func 를 import 한다.
    cwd_backup = Path.cwd()
    sys.path.insert(0, str(notebook_dir))
    import os

    os.chdir(notebook_dir)
    try:
        namespace = run_notebook(notebook_path, namespace, log)
    except Exception:
        log.error("노트북 실행 중 오류로 중단합니다. 스냅샷을 만들지 않았습니다.")
        return 1
    finally:
        os.chdir(cwd_backup)

    if not namespace.get("go_ahead", False):
        log.error("go_ahead=False — mp_start_date 가 저장된 MP 기준일보다 빠릅니다.")
        return 1

    # 비교기간 기준일 (원본 Performance_Analysis_Module CELL 16~18)
    try:
        from performance_monitor.src.data_loader import DbSource

        source = DbSource(config)
        anchors = source.load_period_anchors(mp_end_date)
        source.close()
        for key, var in (("MTD", "mtd_date"), ("QTD", "qtd_date"), ("HTD", "htd_date"),
                         ("YTD", "ytd_date"), ("1Y", "y1_date")):
            if anchors.get(key):
                namespace[var] = anchors[key]
        log.info(f"비교기간 기준일 {anchors}")
    except Exception as exc:  # noqa: BLE001
        log.warning(f"비교기간 기준일 조회 실패 (기간별 표가 비게 됩니다): {exc}")

    final_mp = namespace.get("final_mp")
    log.info(
        f"Data loaded | Portfolio: "
        f"{final_mp.index.get_level_values('item').nunique()} stocks | "
        f"Benchmark: {args.benchmark} | "
        f"Period: {report_start_date} ~ {mp_end_date}"
    )

    path = export(namespace, slim=not args.full)
    log.info(f"Analysis completed | {path}")

    rcf = namespace["return_contribution_final"]
    top = config.top_model_column(args.benchmark) or rcf.columns[-1]
    if top in rcf.columns:
        log.info(
            f"{top} | total {float(rcf.loc['total', top]):.4%} "
            f"| bm {float(rcf.loc['bm', top]):.4%} "
            f"| active {float(rcf.loc['active', top]):.4%}"
        )
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mp-start-date", default="2023-02-13",
                        help="데이터 시작일 (원본 기본값 2023-02-13)")
    parser.add_argument("--report-start-date", help="리포트 기준일 = 직전 주 마지막 영업일")
    parser.add_argument("--mp-end-date", help="분석 종료일")
    parser.add_argument("--benchmark", default="kospi200", choices=["kospi200", "kospi"])
    parser.add_argument("--auto", action="store_true",
                        help="DB 에서 직전 영업일/전주 마지막 영업일을 자동 결정")
    parser.add_argument("--bm-pre-rebal", action="store_true",
                        help="BM 정기변경 선반영 (원본 bm_pre_rebal=True)")
    parser.add_argument("--rebal-end-dt", help="마지막 리밸런싱 일자 (bm_pre_rebal 사용 시)")
    parser.add_argument("--bm-reb-date", help="BM 변경 반영일 (bm_pre_rebal 사용 시)")
    parser.add_argument("--notebook-dir", help="노트북 디렉터리 (기본: performance_monitor/notebooks)")
    parser.add_argument("--full", action="store_true",
                        help="final_mp 전체 컬럼 저장 (기본은 대시보드용 컬럼만)")
    sys.exit(main(parser.parse_args()))
