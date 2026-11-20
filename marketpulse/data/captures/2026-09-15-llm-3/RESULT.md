status=OK
llm_status=degraded
state=RISK_OFF conf=87
narrative_source=template
coverage=34/47
news=60 extractors=['rule'] llm_events=0
thermometer=-19.171862394768993 price=-33.588762605888824 news_temp=2.4534879219107526
warnings:
  - 13개 instrument 미확보: KRX_SEMI, KR3Y, KR10Y, BE10Y, VKOSPI…
  - KRX_SEMI: krx HTTP 403 Forbidden
  - KR3Y: krx HTTP 403 Forbidden
  - KR10Y: krx HTTP 403 Forbidden
  - BE10Y: fred FRED_API_KEY 가 없다. https://fred.stlouisfed.org/docs/api/api_key.html
  - … 외 9개 종목도 같은 이유로 실패
  - 뉴스 피드 이데일리 마켓: 연결 실패: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1016)
  - 뉴스 피드 Reuters Business: 연결 실패: Tunnel connection failed: 502 Bad Gateway
notes:
  - LLM 호출 자체는 도달했으나 API 가 400 "credit balance is too low" 로 거절 (요청 3건 후 회로 차단). 키·네트워크 문제 아님, 계정 크레딧 문제.
  - 소형 테스트 호출(max_tokens=20)은 2.2초에 성공. web_search 도구 호출과 추출 호출은 모두 크레딧 거절.
  - probe.txt 의 LLM 검색 실패(timeout)는 SDK 재시도 중 8초 제한 초과; 재검사에서 같은 크레딧 400.
