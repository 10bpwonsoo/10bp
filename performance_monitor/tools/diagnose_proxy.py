"""붙여넣기용 셀 — 프록시 404 원인을 찾는다.

Jupyter 주소로 대시보드에 들어갔을 때 404 가 나면, 원인이 여러 갈래다.
어느 쪽인지 추측하지 않고 한 번에 확인한다.

    1. 지금 import 된 코드가 새 버전인가 (설치 경로가 여러 개면 옛 것을 볼 수 있다)
    2. jupyter-server-proxy 가 서버에 **enabled** 로 등록돼 있는가
    3. streamlit 이 실제로 떠 있고 루트('/')에서 응답하는가
    4. 프록시 경로에서 404 를 내는 것이 Jupyter 인가 streamlit 인가

이 파일 내용을 노트북 셀에 그대로 붙여넣고 실행한 뒤, 출력을 알려주십시오.
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

print("=" * 66)
print("1) 지금 돌고 있는 코드")
print("=" * 66)
try:
    import pm_engine as pm
    from src import launcher
    print("  pm_engine :", pm.__file__)
    print("  launcher  :", launcher.__file__)
    new_code = hasattr(launcher, "_display_link")
    print("  버전      :", "새 버전 ✓" if new_code else "옛 버전 ✗  ← 이것이 원인입니다")
    if not new_code:
        print("    부트스트랩이 다른 폴더에 설치됐거나 커널을 재시작하지 않은 것입니다.")
        print("    위 launcher 경로에 부트스트랩을 설치한 뒤 커널을 재시작하십시오.")
except Exception as exc:
    print("  pm_engine 을 불러오지 못했습니다:", exc)
    raise SystemExit

print()
print("=" * 66)
print("2) jupyter-server-proxy 등록 상태")
print("=" * 66)
try:
    out = subprocess.run([sys.executable, "-m", "jupyter", "server", "extension", "list"],
                         capture_output=True, text=True, timeout=60)
    text = (out.stdout or "") + (out.stderr or "")
    for line in text.splitlines():
        if "proxy" in line.lower() or "enabled" in line.lower() or "Config" in line:
            print("  ", line.strip())
    if "jupyter_server_proxy" not in text:
        print("   ✗ jupyter_server_proxy 가 목록에 없습니다.")
except Exception as exc:
    print("  확인 실패:", exc)

print()
print("=" * 66)
print("3) streamlit 서버 상태")
print("=" * 66)
status = pm.dashboard_status()
print("  ", status)
port = status.get("port") if isinstance(status, dict) else None
if not port:
    port = 8501
    print("   실행 중이 아닙니다. pm.launch_dashboard() 를 먼저 실행하십시오.")


# localhost 요청이 사내 프록시로 새지 않게 한다. 안 그러면 프록시가 돌려준
# 404 를 서버의 404 로 착각한다.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(url, note=""):
    request = urllib.request.Request(url)
    try:
        with _opener.open(request, timeout=8) as response:
            body = response.read(200).decode("utf-8", "replace").replace("\n", " ")
            print(f"   {url}\n      {response.status}  {body[:120]}  {note}")
            return response.status
    except urllib.error.HTTPError as exc:
        body = exc.read(300).decode("utf-8", "replace").replace("\n", " ")
        who = ("Jupyter" if ("jupyter" in body.lower() or "tornado" in body.lower())
               else "streamlit" if "streamlit" in body.lower() else "?")
        print(f"   {url}\n      {exc.code}  [{who}]  {body[:160]}  {note}")
        return exc.code
    except Exception as exc:
        print(f"   {url}\n      실패: {type(exc).__name__}: {exc}  {note}")
        return None


print()
print("   streamlit 에 직접 (프록시 없이)")
fetch(f"http://127.0.0.1:{port}/", "← 200 이어야 정상")

print()
print("=" * 66)
print("4) 프록시 경로 — 404 를 누가 내는가")
print("=" * 66)
service_url = os.environ.get("JUPYTERHUB_SERVICE_URL", "")
prefix = os.environ.get("JUPYTERHUB_SERVICE_PREFIX", "/")
print("   JUPYTERHUB_SERVICE_URL   :", service_url or "(없음)")
print("   JUPYTERHUB_SERVICE_PREFIX:", prefix)

base = ""
if service_url:
    from urllib.parse import urlparse
    parsed = urlparse(service_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
else:
    try:
        out = subprocess.run([sys.executable, "-m", "jupyter", "server", "list", "--json"],
                             capture_output=True, text=True, timeout=30)
        for line in out.stdout.splitlines():
            info = json.loads(line)
            base = f"http://127.0.0.1:{info['port']}"
            prefix = info.get("base_url", prefix)
            break
    except Exception as exc:
        print("   jupyter server list 실패:", exc)

if base:
    print("   Jupyter 주소:", base + prefix)
    print()
    for path in (f"{prefix}proxy/{port}/",
                 f"{prefix}proxy/absolute/{port}/",
                 f"{prefix}api/status"):
        fetch(base + path)
else:
    print("   Jupyter 주소를 알아내지 못했습니다.")

print()
print("=" * 66)
print("위 출력 전체를 그대로 알려주십시오.")
print("=" * 66)
