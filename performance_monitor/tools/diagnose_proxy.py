"""프록시 404 원인 진단.

    %run <설치경로>/tools/diagnose_proxy.py

네 가지를 확인한다.
  1. 지금 import 된 코드가 새 버전인가 (설치 폴더가 여러 겹이면 옛 것을 볼 수 있다)
  2. jupyter-server-proxy 가 서버에 enabled 로 등록됐는가
  3. streamlit 이 루트('/')에서 200 을 주는가
  4. 프록시 경로의 404 를 Jupyter 가 내는가 streamlit 이 내는가
"""
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# 이 파일이 속한 설치본을 경로에 넣는다. 다만 이미 import 된 pm_engine 이
# 있으면 sys.modules 캐시가 이긴다 — 그게 지금 실제로 돌고 있는 코드이므로
# 진단 목적에 맞다.
try:
    _ROOT = Path(__file__).resolve().parent.parent
except NameError:
    _ROOT = Path.cwd()
for _path in (str(_ROOT), str(_ROOT / "notebooks")):
    if _path not in sys.path:
        sys.path.append(_path)

# localhost 요청이 사내 프록시로 새면 거짓 404 가 보고된다.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(url):
    try:
        response = OPENER.open(url, timeout=8)
        body = response.read(160).decode("utf-8", "replace")
        print("   %-52s %s" % (url, response.status))
        return response.status
    except urllib.error.HTTPError as exc:
        body = exc.read(400).decode("utf-8", "replace").lower()
        who = "?"
        if "jupyter" in body or "tornado" in body:
            who = "Jupyter 가 냄"
        elif "streamlit" in body:
            who = "streamlit 이 냄"
        print("   %-52s %s  %s" % (url, exc.code, who))
        return exc.code
    except Exception as exc:
        print("   %-52s 실패 %s" % (url, exc))
        return None


print("=" * 64)
print("1) 지금 돌고 있는 코드")
import pm_engine as pm
from src import launcher

print("   pm_engine :", pm.__file__)
print("   launcher  :", launcher.__file__)
if hasattr(launcher, "_display_link"):
    print("   버전      : 새 버전 OK")
else:
    print("   버전      : 옛 버전  <<< 이것이 원인입니다")
    print("   위 launcher 경로에 부트스트랩을 설치하고 커널을 재시작하십시오.")

print()
print("=" * 64)
print("2) jupyter-server-proxy 등록 상태")
try:
    out = subprocess.run(
        [sys.executable, "-m", "jupyter", "server", "extension", "list"],
        capture_output=True, text=True, timeout=60)
    text = out.stdout + out.stderr
    for line in text.splitlines():
        if "proxy" in line.lower():
            print("  ", line.strip())
    if "jupyter_server_proxy" not in text:
        print("   목록에 없습니다 <<< 서버에 등록되지 않았습니다")
except Exception as exc:
    print("   확인 실패:", exc)

print()
print("=" * 64)
print("3) streamlit 서버")
status = pm.dashboard_status()
print("  ", status)
port = 8501
if isinstance(status, dict) and status.get("port"):
    port = status["port"]
fetch("http://127.0.0.1:%d/" % port)

print()
print("=" * 64)
print("4) 프록시 경로")
prefix = os.environ.get("JUPYTERHUB_SERVICE_PREFIX", "/")
service = os.environ.get("JUPYTERHUB_SERVICE_URL", "")
print("   PREFIX :", prefix)
print("   URL    :", service or "(없음)")

base = ""
if service:
    parts = service.split("/")
    base = parts[0] + "//" + parts[2]
else:
    try:
        out = subprocess.run(
            [sys.executable, "-m", "jupyter", "server", "list"],
            capture_output=True, text=True, timeout=30)
        for line in (out.stdout + out.stderr).splitlines():
            if "http://" in line:
                url = line.split()[0]
                parts = url.split("/")
                base = parts[0] + "//" + parts[2]
                print("   server list :", url)
                break
    except Exception as exc:
        print("   jupyter server list 실패:", exc)

if base:
    fetch(base + prefix + "api/status")
    fetch(base + prefix + "proxy/%d/" % port)
    fetch(base + prefix + "proxy/absolute/%d/" % port)
else:
    print("   Jupyter 주소를 알아내지 못했습니다.")

print()
print("=" * 64)
print("위 출력을 그대로 알려주십시오.")
