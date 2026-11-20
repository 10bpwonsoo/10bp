# 정책·지표 이벤트 파일 매일 갱신 절차

금리 탭 POLICY & MACRO EVENTS 는 `marketpulse/data/policy_events/YYYY-MM-DD.json`(KST 날짜)에서만 값을 읽는다.
스냅샷은 그 날짜 이하의 가장 최근 파일을 쓰므로, 파일을 매일 이어 쓰지 않으면 화면이 옛 결정에 멈춘다(2026-10-16 ~ 11-04 에 실제로 그랬다).

평일 06:40 KST 에 예약 작업이 아래 순서로 돈다. 07:30 KST 스냅샷보다 먼저 끝나야 그날 스냅샷이 새 파일을 읽는다.

## 순서

1. 브랜치 `claude/market-pulse-ai-design-r7pmsm` 최신으로. 가상환경: `python3 -m venv .venv && .venv/bin/pip install -q -e .`
2. `.venv/bin/python -m marketpulse.scripts.policy_events_update draft`
   - 오늘(KST) 파일이 없으면 직전 파일을 이어 쓴다(collected 만 오늘, 값은 그대로). 결과가 이미 들어간 지난 일정 · 판정 항목이 없는 지난 일정(PPI · 소매판매 등)은 upcoming 에서 뺀다.
   - 출력 = 조사 목록(due): 날짜가 지났는데 결과가 파일에 없는 일정.
3. 조사 — due 항목마다, 그리고 일정에 없던 결정(긴급 회의 등)이 있었는지 웹검색으로 확인한다.
   - **같은 숫자를 둘 이상 독립 보도(또는 공식 발표)로 확인한 값만** 적는다. 확인 못 한 값은 `null`(숫자) · `""`(문장)으로 둔다 — 0 이 아니다. 추정 · 보간 금지.
   - 중앙은행(FED · ECB · BOJ · BOK) — 은행마다 **최신 결정 하나**로 바꾼다: decision(HIKE/HOLD/CUT) · change_bp · previous_rate(= 직전 current_rate) · current_rate · vote · guidance(hawkish/neutral/dovish, 근거는 guidance_basis 에) · statement · chair · projections · market_path · line · next_meeting(_start) · implication · sources.
   - 발표(us_cpi · us_pce · us_nfp) — releases 에 **더한다**(지운 발표가 있으면 검사가 막는다): period(YYYY-MM) · date(발표일) · consensus_source · measures(actual · consensus · prior · note) · note · sources. 컨센서스는 출처마다 다르면 어느 출처인지 consensus_source 에 쓰고 다른 값은 note 에.
   - 결과를 넣은 일정은 upcoming 에서 빼고, 새로 알게 된 일정(다음 회의 · 다음 발표)은 출처와 함께 더한다. 미국 발표는 `release_utc` 를 적는다.
   - note 첫 문장에 오늘 무엇을 더했는지 적는다. 새 결과가 없으면 그대로 둔다.
   - 문장에 '확률' · '매수' · '매도' · '전망' 이라는 말을 쓰지 않는다.
4. `.venv/bin/python -m marketpulse.scripts.policy_events_update validate` — 오류 0 이어야 한다.
   - 형식 · look-ahead(파일 날짜 당일 이후의 결정 · 발표 금지) · 금리 산술(current − previous = change_bp) · 출처 · 직전 파일 대비 빠진 은행/발표.
   - FRED 대조(발표일 vintage): CPI · PCE · 고용 actual, 연준 목표 상단 · ECB 예치금리. 불일치면 보도를 다시 확인하고, 그래도 안 맞으면 그 값을 `null` 로 두고 note 에 이유를 쓴다. FRED 값으로 덮어쓰지 않는다(보도 숫자 칸이다).
5. `.venv/bin/python -m pytest -q tests/test_policy_events_update.py tests/test_policy_events.py`
6. 이벤트 파일 하나만 커밋해 브랜치에 push 한다. 저장본(archive) · 캡처 · 다른 파일은 건드리지 않는다 — 저장본은 잠금이고 고치려면 사용자 승인 뒤 `archive correct` 경로만.

새 결과가 없는 날도 이어 쓴 파일을 커밋한다(수집 날짜가 화면 하단에 보인다).
