# 2026-09-14 LLM 실데이터 캡처 — 미실행

status=SKIPPED
reason=ANTHROPIC_API_KEY unset

## 확인 내용
- 세션 환경변수에 `ANTHROPIC_API_KEY` 가 없다 (`[ -n "$ANTHROPIC_API_KEY" ]` → unset).
- `env` 에 ANTHROPIC 관련 변수는 `ANTHROPIC_BASE_URL` 하나뿐이다 (값은 기록하지 않음).
- 저장소 루트에 `.env` 파일도 없다 (`.env.example` 만 존재).
- `marketpulse/config/settings.py:53-54` 는 `ANTHROPIC_API_KEY` 존재 여부로 `llm_enabled` 를 정하므로,
  이 환경에서는 `Settings(data_mode="DELAYED").llm_enabled == False` 가 된다.

## 실행하지 않은 단계
- `probe --mode DELAYED --llm-search` (probe.txt 없음)
- 실데이터 두 틱 캡처 (live.json / news_live.json 없음)

## notes
- 코드 로직은 변경하지 않았다.
- 세션 환경에 `ANTHROPIC_API_KEY` 를 넣은 뒤 같은 절차를 다시 돌리면 된다.
