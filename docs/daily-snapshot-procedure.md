# Daily Snapshot 매일 절차 (평일 07:30 KST 기준)

한국 평일 아침마다 그날 07:30 KST cutoff 의 대시보드 전체를 만들어 저장(archive · history 행)하고 정적 배포본을 갱신한다.
도구는 `tools/daily_snapshot/`, 저장소 루트에서 실행한다. 이 문서의 규칙은 지금까지(10/12~11/10) 손으로 한 절차를 그대로 옮긴 것이다.

## 지킬 것

- 데이터가 없으면 비워 둔다(0 아님). 보간 · 앞값 채우기 · 단위 보정 금지. Yahoo 에 그날 일봉이 없으면 결측 그대로.
- cutoff 이후 봉 · 기사는 쓰지 않는다(재구성 코드가 자르지만, extra_news 를 더할 때는 직접 확인).
- 저장본 · 잠긴 history 행은 고치지 않는다. 고칠 일이 생기면 사용자 승인 뒤 `archive correct` 로만(이전 파일은 superseded/).
- 화면 · 문장에 '확률' · '매수' · '매도' · '전망' 을 쓰지 않는다. API 키 값은 출력하지 않는다.
- 해석 4종(금리 MARKET READ · 물가 해석 · 반도체 MARKET READ · REGIME v2 선택)은 API 가 되면 파이프라인이 만든다. API 가 안 되면(지금까지 계속 401) 이 세션이 **같은 컨텍스트 · 같은 프롬프트 · 같은 검증**으로 `*_session.json` 을 쓴다 — 검증을 통과해야만 쓰이고 화면에 '세션 생성' 으로 표시된다.
- 다른 탭 화면 코드는 건드리지 않는다. 오류를 발견하면 고치되, 그날 보고에 무엇을 왜 바꿨는지 적는다.

## 순서 (D = 오늘 KST 날짜, P = 작업 폴더 — 세션 scratchpad 의 pit/)

1. 브랜치 `claude/market-pulse-ai-design-r7pmsm` 최신으로. `.venv` 없으면 `python3 -m venv .venv && .venv/bin/pip install -q -e .`, `frontend/node_modules` 없으면 `cd frontend && npm ci`.
   `python -m marketpulse.archive plan` 으로 D 가 MISSING 인지 확인(주말 · 이미 저장된 날이면 하지 않는다).
2. 메모리 가격: `python -m marketpulse.scripts.collect_memory_prices --only semi` · `python -m marketpulse.scripts.collect_memory_history daily-express --latest` → 바뀐 CSV 를 커밋.
3. 입력 수집: `python -m marketpulse.archive fetch-inputs P/inputs_D`. `fetch_report.json` 을 전날 입력과 비교해 빠진 계열이 있으면(Yahoo 429)
   잠시 뒤 재수집 · `tools/daily_snapshot/fetch_missing.py` 로 빠진 것만 간격을 두고 받고 `merge_inputs.py` 로 합친다(계열마다 마지막 봉이 가장 늦은 것).
   **전날 수집분은 합치지 않는다** — 수집 시점의 장중 봉이 섞인다.
4. `tools/daily_snapshot/scan_units.py P/inputs_D` — 단위 불연속(분할 조정 혼재 등)이 있으면 그 계열을 빼고 이유를 캡처 폴더 `input_merge_report.json` 에 남긴다. VIX 처럼 실제로 큰 움직임은 기사로 확인하고 둔다.
5. 뉴스: 전날 합친 RSS 와 오늘 수집분을 id 로 합쳐 `P/inputs_D/news_rss.json` 에 둔다. 창(전 영업일 07:30 ~ D 07:30 KST, 주말 포함)의 기사를 읽고
   시장 관련 기사만 `marketpulse/data/captures/D-backfill/manual_tags.json` 에 수기 태깅(themes 는 config/themes.yaml 의 id, theme_direction 은 up/down 만 — 0 은 테마에서 뺀다). 커밋.
6. `python tools/daily_snapshot/build_day.py D P/inputs_D context` → 캡처 폴더의 `rates_read_context.json` · `semiconductor_read_context.json` · `regime_select_context.json`(물가 해석은 rates 컨텍스트의 inflation_map).
   각 컨텍스트만 읽고 세션본을 쓴 뒤 검증한다:
   `ai.rates_read.check_output(normalize_output(..))` · `ai.inflation_read.check(read, ctx['inflation_map'])` · `ai.semi_read.check_output(..)` · `engines.regime_select.check_output(..)` — 모두 빈 목록이어야 한다.
   지난 세션본(예: `captures/2026-11-10-backfill/*_session.json`)의 형식 · 어조를 따른다. 숫자는 컨텍스트 값만, displayed_elsewhere 숫자는 쓰지 않는다.
   REGIME v2: 자격 후보(또는 NEUTRAL)만 고른다. confidence 는 정량값을 그대로 옮기지 말고 근거(데이터 지연 · 한국 결측 · 하루짜리 이벤트)를 따져 정하고, 이유를 selection_rationale 에 쓴다.
7. `python tools/daily_snapshot/build_day.py D P/inputs_D full` → `python -m marketpulse.archive validate D`(COMPLETE).
   history 7개 파일이 **새 행 1개씩만** 늘었는지(기존 행 변화 0) 확인한다 — 아니면 커밋하지 말고 원인부터.
8. `.venv/bin/python -m pytest -q -p no:warnings` 전부 통과.
9. 배포본: `cd frontend && npm run build`, `python tools/daily_snapshot/build_bundle.py marketpulse/data/captures/D-backfill "D Daily Snapshot (07:30 KST) · 미국 <전 영업일> 종가 기준" P/dash/index.html`,
   `python3 -m http.server` 로 띄워 `node tools/daily_snapshot/check_screen.cjs <url> marketpulse/data/archive/screenshots/D.jpg` — 오류 0 · 가로 스크롤 없음 · 금리 탭 '수집 D'.
10. `docs/01-session-summary-2026-09-16.md` 에 그날 절(입력 · 결측 · 결과 · history) 추가 → 커밋 · push(네트워크 오류는 2·4·8·16초 재시도).
11. 배포: Artifact 를 **https://claude.ai/artifact/3ERLmXjNkcrbGmfdjwbHzS** 로만 갱신(다른 주소에 올리지 않는다).
12. 한국어로 짧게 보고: 입력 커버리지 · 결측, 오늘 regime(선택 · 공식 · 전환), 탭별 판정 한 줄씩, 고친 것, 커밋 · 배포 버전.
