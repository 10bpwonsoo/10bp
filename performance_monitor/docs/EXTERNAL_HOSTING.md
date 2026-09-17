# 사외 호스팅 — 내부에서 계산, 밖에서 대시보드

내부에서 계산한 결과를 **스냅샷 번들**로 내보내고, 사외 서버에서 **같은
Streamlit 대시보드**를 그 번들만 가지고 띄운다. 필터·드릴다운·8개 메뉴가
전부 그대로 동작한다.

```
  [사내]                                   [사외]
  노트북 실행                               Streamlit
      ↓                                        ↑
  pm.export_snapshot(globals())            PM_DATA_DIR
      ↓                                        ↑
  pm.export_bundle()  ──  pm_bundle_*.zip  ──→ 압축 해제
```

**대시보드는 DB 에 붙지 않는다.** `PM_DATA_DIR` 아래 스냅샷 폴더만 읽는다.
사외 서버에 사내 DB 접근 권한이 필요 없고, `jackhammer`·`vrksa` 도 필요 없다.
필요한 것은 `requirements.txt` 뿐이다.

---

## 1. 사내에서 — 번들 만들기

주간 노트북을 끝까지 실행한 뒤, 같은 커널에서:

```python
pm.export_snapshot(globals())    # 스냅샷
pm.export_bundle()               # 번들 zip
```

```
번들 생성: data/bundles/pm_bundle_20260904_full.zip  (6.6 MB)
  기준일 2026-09-04 · level=full · 종목 60
```

종목 식별자를 가리고 싶으면:

```python
pm.export_bundle(level='anonymous')   # A005930 -> STOCK_0001
```

대조용 매핑은 **사내에만** 남는다(`data/bundles/mapping_*.json`). zip 에는 들어가지
않는다. 다만 업종과 일별 수익률이 남으므로, 시장 데이터를 가진 사람은 수익률
계열을 맞춰 역추적할 수 있다. 일반 열람자 기준의 가림막이다.

---

## 2. 사외 서버에서 — 처음 한 번

```bash
# 코드
unzip performance_monitor_win.zip -d /srv
cd /srv/performance_monitor

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 데이터
mkdir -p /srv/pm
unzip pm_bundle_20260904_full.zip -d /srv/pm      # -> /srv/pm/data/processed/...
```

실행:

```bash
PM_DATA_DIR=/srv/pm/data .venv/bin/streamlit run app.py \
    --server.port 8501 --server.address 0.0.0.0 --server.headless true
```

또는 동봉된 스크립트:

```bash
./run_external.sh /srv/pm/data 8501
```

---

## 3. 매주 갱신

번들만 바꿔 끼우면 된다. 코드는 그대로다.

```bash
unzip -o pm_bundle_20260911_full.zip -d /srv/pm
```

Streamlit 재시작도 필요 없다. 사이드바 **데이터 기준일** 에 새 스냅샷이
자동으로 뜬다 (파일명을 하드코딩하지 않고 `manifest.json` 의 `as_of` 로 판단한다).
여러 주치를 함께 두면 화면에서 골라 볼 수 있다.

---

## 4. 접근 통제 — 반드시 앞단에 둘 것

**Streamlit 에는 로그인이 없다.** 포트에 닿는 사람은 누구나 본다.
사외에 두려면 앞단에 인증을 반드시 세워야 한다.

| 방식 | 비고 |
|---|---|
| 사내 게이트웨이/리버스 프록시 + SSO | 권장. IT 가 이미 운영 중일 것이다 |
| nginx basic auth + HTTPS | 가장 간단. 최소한 이것은 있어야 한다 |
| 클라우드 VM + 보안그룹 IP 제한 | 접속 IP 를 아는 경우 |

`Streamlit Community Cloud` 는 **기본이 공개**다. 비공개 앱으로 설정할 수 있는
요금제가 아니면 쓰지 말 것.

nginx 예시:

```nginx
server {
    listen 443 ssl;
    server_name pm.example.com;

    auth_basic "MP Performance";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;     # websocket 필수
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

`Upgrade`/`Connection` 헤더가 없으면 화면이 멈춘 것처럼 보인다. Streamlit 은
websocket 으로 동작한다.

---

## 5. 확인된 것

번들만 있는 폴더(사내 DB·네트워크 없음)를 가리켜 8개 페이지를 전부 실행했다.

```
app.py                       OK
pages/1_Performance.py       OK
pages/2_Attribution.py       OK
pages/3_Models.py            OK
pages/4_Stocks.py            OK
pages/5_Position_Change.py   OK
pages/6_Data_Validation.py   OK
pages/7_Export.py            OK
```

번들 왕복 시 숫자가 바뀌지 않는 것은 `tests/test_external_bundle.py` 로 고정했다.

---

## 6. 반출 승인

번들에는 모델 포트폴리오의 종목과 비중이 들어 있다. 사외 반출은
**정보보호팀 승인 사항**이다. 이 도구는 무엇을 담을지 고를 수 있게 할 뿐이다.
