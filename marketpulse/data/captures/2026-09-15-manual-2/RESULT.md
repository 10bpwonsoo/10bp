# 2026-09-15 01:37 UTC 수기 캡처 2차 — API 크레딧 미사용

status=OK (API 호출 0건)

- 시장데이터: Yahoo/GitHub 무료 공급자, 34/47.
- 뉴스: RSS 80건(한경 50·매경 33·CNBC 30·Investing 10·연합 3, 중복 제거) +
  이 세션의 웹검색으로 찾은 해외 기사 12건(CNBC·Reuters/Investing·CNN·Fortune·
  Quartz·Yahoo Finance·Rigzone·invezz·Chase). 해외 검색 기사는 제목·URL·게시일만
  검색 결과에서 가져왔고 시각은 일 단위라 12:00 UTC 로 두었다(quality=PARTIAL).
- 태깅: 1차 28건을 이어받고 20건을 새로 읽어 총 48건(국내 36 + 해외 12).
  extractor="manual". geopolitical_risk 는 risk 극성이라 긴장 고조를 +로 고쳤다.
- Google News RSS 4종을 feeds.yaml 에 추가했다. news.google.com 이 허용 목록에
  없어 지금은 실패하고, 허용되면 자동으로 붙는다.

## 결과
- RISK_OFF 87% · 온도계 -34(가격 -34 / 뉴스 -33, 격차 없음) · 괴리 6건 · 알림 7건
- 테마 히트맵의 각 행을 누르면 그 테마로 태그된 기사 상위 4건(영향도 순)이 펼쳐지고
  헤드라인이 원문으로 링크된다. NewsEvent 에 url 필드를 더했다.

## 한계 (1차와 같다)
- 자동화 파이프라인이 아니다. 매 틱 재현되지 않는다.
- Oil/Rates 의 sentiment 축은 "거시적으로 나쁜 뉴스 = 음수" 로 읽었다.
- Oil·Semiconductor 괴리 일부는 KRX 결측(한국 반도체 지표 부재) 탓일 수 있다.
