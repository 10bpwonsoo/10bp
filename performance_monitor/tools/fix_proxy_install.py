"""jupyter-server-proxy 를 **Jupyter 서버의 파이썬**에 설치한다.

커널과 Jupyter 서버가 서로 다른 환경인 경우가 있다 (TLJH 가 그렇다).
커널에 설치하면 `import jupyter_server_proxy` 는 되지만 서버는 모르므로
`/proxy/<포트>/` 가 404 가 난다.

    %run <설치경로>/tools/fix_proxy_install.py

하는 일
  1. 실행 중인 Jupyter 서버 프로세스를 찾아 그 파이썬을 알아낸다
  2. 그 파이썬이 jupyter_server_proxy 를 import 할 수 있는지 본다
  3. 못 하면 --user 로 설치를 시도하고 다시 확인한다
  4. 그래도 안 되면 관리자에게 줄 명령을 출력한다

설치 후에는 **Jupyter 서버를 재시작**해야 한다 (커널 재시작이 아니다).
"""
import os
import subprocess
import sys

MARKERS = ("jupyterhub-singleuser", "jupyter-labhub", "singleuser",
           "jupyter-lab", "jupyter-server", "jupyter-notebook")


def find_server_python():
    """실행 중인 Jupyter 서버의 파이썬 경로."""
    found = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open("/proc/%s/cmdline" % pid, "rb") as handle:
                cmd = handle.read().decode("utf-8", "replace")
        except (OSError, IOError):
            continue
        if not any(marker in cmd for marker in MARKERS):
            continue
        try:
            exe = os.readlink("/proc/%s/exe" % pid)
        except (OSError, IOError):
            continue
        found.append((pid, exe, cmd.replace("\x00", " ").strip()))
    return found


def can_import(python):
    try:
        out = subprocess.run([python, "-c", "import jupyter_server_proxy, sys;"
                              "print(sys.prefix)"],
                             capture_output=True, text=True, timeout=60)
        return out.returncode == 0, (out.stdout + out.stderr).strip()
    except Exception as exc:
        return False, str(exc)


print("=" * 64)
print("1) Jupyter 서버 프로세스")
servers = find_server_python()
if not servers:
    print("   찾지 못했습니다. 아래 경로를 직접 확인하십시오:")
    print("      /opt/tljh/user/bin/python")
    targets = ["/opt/tljh/user/bin/python"]
else:
    targets = []
    for pid, exe, cmd in servers:
        print("   pid %-8s %s" % (pid, exe))
        print("      %s" % cmd[:110])
        if exe not in targets:
            targets.append(exe)

print()
print("   커널의 파이썬 :", sys.executable)

print()
print("=" * 64)
print("2) 서버 파이썬이 jupyter_server_proxy 를 import 할 수 있는가")
need_install = []
for python in targets:
    ok, detail = can_import(python)
    print("   %-45s %s" % (python, "OK" if ok else "불가"))
    if ok:
        print("      sys.prefix:", detail)
    else:
        need_install.append(python)

already_ok = not need_install
if already_ok:
    print()
    print("   모두 import 가능합니다. 등록만 하면 됩니다:")
    for python in targets:
        subprocess.run([python, "-m", "jupyter", "server", "extension",
                        "enable", "--user", "jupyter_server_proxy"],
                       capture_output=True, text=True, timeout=120)
        print("      ~/.jupyter 에 등록:", python)

print()
print("=" * 64)
print("3) --user 로 설치 시도 (관리자 권한 없이)")
if already_ok:
    print("   설치할 것이 없습니다.")
for python in list(need_install):
    print("   대상:", python)
    try:
        out = subprocess.run([python, "-m", "pip", "install", "--user",
                              "jupyter-server-proxy"],
                             capture_output=True, text=True, timeout=600)
        tail = (out.stdout + out.stderr).strip().splitlines()
        for line in tail[-6:]:
            print("     ", line)
    except Exception as exc:
        print("      실패:", exc)
        continue
    ok, detail = can_import(python)
    print("      재확인:", "OK" if ok else "여전히 불가")
    if ok:
        need_install.remove(python)
        subprocess.run([python, "-m", "jupyter", "server", "extension",
                        "enable", "--user", "jupyter_server_proxy"],
                       capture_output=True, text=True, timeout=120)
        print("      ~/.jupyter 에 등록했습니다.")

print()
print("=" * 64)
if need_install:
    print("4) 권한이 없어 설치하지 못했습니다. 관리자에게 아래를 요청하십시오.")
    for python in need_install:
        prefix = python.rsplit("/bin/", 1)[0]
        print()
        print("   sudo %s -m pip install jupyter-server-proxy" % python)
        print("   sudo %s/bin/jupyter server extension enable "
              "--sys-prefix jupyter_server_proxy" % prefix)
    print("   sudo tljh-config reload     # TLJH 인 경우")
    print()
    print("   설치가 어려우면 pm.report() 를 쓰십시오. 노트북 안에 그려집니다.")
else:
    print("4) 준비 완료.")
    print("   이제 **Jupyter 서버를 재시작**하십시오 (커널 재시작 아님):")
    print("      File > Hub Control Panel > Stop My Server > Start My Server")
    print("   재시작 후 pm.launch_dashboard() 를 다시 실행하십시오.")
print("=" * 64)
