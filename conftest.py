"""
리포지토리 루트 conftest.

upbit_trading/ 수집을 확실히 막는다.

왜 필요한가
-----------
upbit_trading/test_sql_load.py 는 파일명만 test_ 로 시작할 뿐 pytest 테스트가
아니다. 함수조차 없는 최상위 스크립트이고, **import 되는 순간**
  · master DB 에 접속하고
  · CREATE DATABASE [CryptoDB] 를 실행하며
  · 테이블을 만들고
  · 라이브 Upbit API 를 호출하고
  · 접속 실패 시 exit(1) 을 부른다.
pyproject 의 testpaths 는 `pytest` 를 인자 없이 돌릴 때만 보호해 준다.
누군가 `pytest .` 를 치면 그 파일이 수집된다. 여기서 한 번 더 막는다.

같은 디렉터리의 test_data_quality.py 도 라이브 Upbit API 를 두드리는
print 기반 스크립트라 함께 제외한다.
"""

collect_ignore_glob = ["upbit_trading/*", ".venv/*", "frontend/*"]
