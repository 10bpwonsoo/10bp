"""노트북 셀에서 Dashboard 서버를 띄운다.

    import pm_engine as pm
    pm.launch_dashboard()      # → http://<이 서버>:8501
    pm.stop_dashboard()

노트북 커널에 streamlit 이 없어도 된다. 프로젝트의 `.venv` 를 찾아
**별도 프로세스**로 띄우므로, 운용 중인 커널 환경(vrksa / jackhammer / 구버전
pandas)을 건드리지 않는다.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from .config import load_config

__all__ = ["launch_dashboard", "stop_dashboard", "dashboard_status", "find_python",
           "detect_jupyter_proxy"]

ROOT = Path(__file__).resolve().parent.parent
_PROCESS: subprocess.Popen | None = None
_URL: str | None = None


def find_python() -> tuple[Path, str]:
    """streamlit 을 실행할 파이썬을 찾는다. ``(경로, 설명)``.

    1. 프로젝트 .venv        ← 권장. 커널 환경과 분리된다
    2. 현재 커널 인터프리터  ← streamlit 이 설치돼 있을 때만
    """
    for candidate in (ROOT / ".venv" / "Scripts" / "python.exe",
                      ROOT / ".venv" / "bin" / "python"):
        if candidate.exists():
            return candidate, f"프로젝트 가상환경 ({candidate})"

    try:
        import streamlit  # noqa: F401

        return Path(sys.executable), f"현재 커널 ({sys.executable})"
    except ImportError:
        pass

    raise RuntimeError(
        "streamlit 을 실행할 파이썬을 찾지 못했습니다.\n"
        f"  프로젝트 위치: {ROOT}\n\n"
        "  아래 중 하나를 하십시오.\n"
        "   (a) 프로젝트 폴더에서 가상환경을 만든다 (권장, 커널 환경과 분리됨)\n"
        "         Windows : py -3.10 -m venv .venv && "
        ".venv\\Scripts\\pip install --no-index --find-links=wheelhouse -r requirements.txt\n"
        "         Linux   : python3 -m venv .venv && "
        ".venv/bin/pip install --no-index --find-links=wheelhouse -r requirements.txt\n"
        "   (b) 커널에 직접 설치한다 (운용 환경을 바꾸므로 권장하지 않음)\n"
        "   (c) 서버를 띄우지 않고 노트북 안에서 본다:  pm.report()"
    )


def detect_jupyter_proxy(port: int | None = None, verbose: bool = False) -> dict:
    """Jupyter 주소를 통해 대시보드에 접속할 수 있는지 확인한다.

    `jupyter-server-proxy` 가 설치돼 있으면, 새 포트를 열지 않고 **이미 열려 있는
    Jupyter 포트**로 대시보드에 들어갈 수 있다. 사내에서 8501 이 막혀 있을 때
    유일하게 현실적인 경로다.

        pm.jupyter_proxy()        # 쓸 수 있는지 확인
    """
    result = {"available": False, "prefix": "/", "base_url_path": "", "path": "",
              "detail": ""}
    try:
        import jupyter_server_proxy  # noqa: F401
    except ImportError:
        result["detail"] = ("jupyter-server-proxy 가 없습니다. "
                            "이 서버에서는 Jupyter 경유 접속을 쓸 수 없습니다.")
        if verbose:
            print(f"✗ {result['detail']}")
            print("  관리자가 설치해 주면 8501 을 열지 않고도 볼 수 있습니다:")
            print("      pip install jupyter-server-proxy   (설치 후 Jupyter 재시작)")
            print("  설치가 어려우면 pm.report() 를 쓰십시오. 노트북 안에 그려집니다.")
        return result

    # JupyterHub 는 사용자별 접두어를 환경변수로 준다 (예: /user/jupyter-soojeon/)
    prefix = os.environ.get("JUPYTERHUB_SERVICE_PREFIX", "/")
    if not prefix.endswith("/"):
        prefix += "/"
    result.update(available=True, prefix=prefix, detail="jupyter-server-proxy 감지됨")
    if port is not None:
        result["base_url_path"] = f"{prefix}proxy/{port}"
        result["path"] = f"{prefix}proxy/{port}/"
    if verbose:
        print(f"✓ {result['detail']}")
        print(f"  Jupyter 접두어: {prefix}")
        print(f"  접속 주소     : <Jupyter 주소>{prefix}proxy/8501/")
        print("  → pm.launch_dashboard() 가 자동으로 이 경로에 맞춰 띄웁니다.")
    return result


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def _free_port(start: int, host: str) -> int:
    for port in range(start, start + 20):
        if not _port_in_use(port, "127.0.0.1"):
            return port
    raise RuntimeError(f"{start}~{start+19} 범위에 빈 포트가 없습니다.")


def _check_network_path() -> None:
    """Streamlit 은 UNC(네트워크) 경로에서 실행되지 않는다."""
    sys.path.insert(0, str(ROOT))
    from tools.preflight import check_network_path

    message = check_network_path()
    if message:
        raise RuntimeError(message)


def launch_dashboard(port: int = 8501, host: str = "0.0.0.0",
                     open_browser: bool = False, wait: float = 25.0,
                     data_dir: str | None = None,
                     jupyter_proxy: bool | None = None) -> str:
    """Dashboard 서버를 백그라운드로 띄우고 접속 주소를 돌려준다.

    Parameters
    ----------
    port           기본 8501. 이미 쓰는 중이면 다음 빈 포트를 자동으로 잡는다
    host           기본 0.0.0.0 (다른 PC 에서도 접속 가능).
                   이 서버에서만 보려면 '127.0.0.1'
    data_dir       스냅샷 위치를 따로 지정 (공유 폴더 등). None 이면 설정값
    jupyter_proxy  Jupyter 주소를 통해 접속한다 (포트가 막혀 있을 때).
                   None 이면 jupyter-server-proxy 설치 여부로 자동 판단.

    포트가 막힌 사내망에서는 ``jupyter_proxy`` 경로가 유일한 현실적 방법이다.
    새 포트를 여는 대신 **이미 열려 있는 Jupyter 포트**로 들어간다. 프록시가
    접두어를 떼고 넘기므로 Streamlit 은 루트에서 서비스하고(baseUrlPath 를 주지
    않는다), 서버는 127.0.0.1 에만 묶는다.
    """
    global _PROCESS, _URL

    if _PROCESS is not None and _PROCESS.poll() is None:
        print(f"이미 실행 중입니다: {_URL}\n중지하려면 pm.stop_dashboard()")
        return _URL

    _check_network_path()
    python, description = find_python()
    port = _free_port(port, host)

    proxy = detect_jupyter_proxy(port)
    if jupyter_proxy is None:
        jupyter_proxy = proxy["available"]
    elif jupyter_proxy and not proxy["available"]:
        raise RuntimeError(
            "jupyter-server-proxy 가 설치돼 있지 않아 Jupyter 경유로 띄울 수 없습니다.\n"
            "  관리자에게 설치를 요청하거나(pip install jupyter-server-proxy),\n"
            "  포트를 못 여는 환경이면 pm.report() 를 쓰십시오."
        )
    if jupyter_proxy:
        # 프록시가 localhost 로 붙으므로 외부에 열 필요가 없다.
        host = "127.0.0.1"

    config = load_config()
    env = dict(os.environ)
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    if data_dir:
        env["PM_DATA_DIR"] = str(data_dir)

    processed = Path(env["PM_DATA_DIR"]) / "processed" if data_dir else config.processed_dir
    snapshots = sorted(processed.glob("snapshot_*")) if processed.exists() else []

    command = [str(python), "-m", "streamlit", "run", str(ROOT / "app.py"),
               "--server.port", str(port), "--server.address", host,
               "--server.headless", "true",
               "--browser.gatherUsageStats", "false"]
    if jupyter_proxy:
        # baseUrlPath 를 주면 안 된다. jupyter-server-proxy 는 '<접두어>proxy/<포트>'
        # 를 **떼고** 백엔드로 넘기므로, streamlit 은 루트에서 서비스해야 한다.
        # (접두어를 주면 프록시가 넘긴 '/' 요청에 대해 streamlit 이 404 를 낸다 —
        #  실제 jupyter-server-proxy 4.5 로 확인했다.)
        # 정적 파일이 상대경로(./static/...)라 접두어 아래에서도 그대로 풀린다.
        # CORS/XSRF 는 프록시를 거치므로 끈다.
        command += ["--server.enableCORS", "false",
                    "--server.enableXsrfProtection", "false"]

    log_path = config.log_dir / "dashboard_server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(log_path, "ab")
    _PROCESS = subprocess.Popen(command, cwd=str(ROOT), env=env,
                                stdout=handle, stderr=subprocess.STDOUT)

    deadline = time.time() + wait
    while time.time() < deadline:
        if _PROCESS.poll() is not None:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-1500:]
            raise RuntimeError(f"서버가 곧바로 종료됐습니다.\n로그: {log_path}\n\n{tail}")
        if _port_in_use(port):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError(f"{wait:.0f}초 안에 뜨지 않았습니다. 로그: {log_path}")

    hostname = socket.gethostname()
    _URL = f"http://localhost:{port}"
    print(f"Dashboard 실행 중  (python: {description})")
    if jupyter_proxy:
        _URL = proxy["path"]
        print(f"  접속 주소        : {proxy['path']}")
        print("                     (새 포트를 열지 않고 Jupyter 포트로 들어갑니다.")
        print("                      주소창의 '/user/…/' 뒷부분을 위 경로로 바꾸면 됩니다)")
    else:
        print(f"  이 서버에서      : http://localhost:{port}")
        if host == "0.0.0.0":
            print(f"  다른 PC 에서     : http://{hostname}:{port}   "
                  f"(방화벽에서 {port} 포트 개방 필요)")
    print(f"  스냅샷           : {processed}  ({len(snapshots)}개)")
    if not snapshots:
        print("  ⚠ 스냅샷이 없어 화면이 비어 보입니다. "
              "pm.export_snapshot(globals()) 를 먼저 실행하십시오.")
    print(f"  로그             : {log_path}")
    print("  중지             : pm.stop_dashboard()")

    if not jupyter_proxy:
        print("  포트가 막혀 있으면: jupyter-server-proxy 설치 후 재시도하거나 "
              "pm.report() 를 쓰십시오.")
    else:
        _display_link(proxy["path"])
    return _URL


def _display_link(path: str) -> None:
    """노트북 출력에 클릭할 수 있는 링크를 띄운다.

    `path` 는 '/' 로 시작하는 절대경로라 브라우저가 현재 호스트에 붙여서
    해석한다. 주소를 손으로 고쳐 치지 않아도 된다. (JupyterLab 은 출력 안의
    <script> 를 실행하지 않으므로 자바스크립트는 쓰지 않는다.)
    """
    try:
        from IPython.display import HTML, display
    except ImportError:  # 노트북 밖에서 호출된 경우
        return
    display(HTML(
        f'<a href="{path}" target="_blank" rel="noopener" '
        'style="display:inline-block;margin:.4rem 0;padding:.45rem .9rem;'
        'background:#d32020;color:#fff;border-radius:4px;font-weight:600;'
        'text-decoration:none;font-family:system-ui,sans-serif">'
        'Dashboard 열기 ↗</a>'
        f'<div style="color:#64748b;font-size:.8rem;font-family:system-ui,sans-serif">'
        f'{path}</div>'))


def stop_dashboard() -> None:
    """실행 중인 Dashboard 서버를 종료한다."""
    global _PROCESS, _URL

    if _PROCESS is None or _PROCESS.poll() is not None:
        print("실행 중인 서버가 없습니다.")
        _PROCESS, _URL = None, None
        return
    _PROCESS.terminate()
    try:
        _PROCESS.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _PROCESS.kill()
    print("Dashboard 를 종료했습니다.")
    _PROCESS, _URL = None, None


def dashboard_status() -> dict:
    """현재 상태."""
    running = _PROCESS is not None and _PROCESS.poll() is None
    return {"running": running, "url": _URL if running else None,
            "pid": _PROCESS.pid if running else None}
