"""정책·지표 이벤트 파일 매일 갱신 스크립트(2026-11-04) — 값을 만들지 않고 이어 쓰기 · 조사 목록 · 검사만 한다."""
import json
from datetime import date

import pytest

from marketpulse.scripts import policy_events_update as U

SRC = [{"title": "t", "url": "https://example.com/a", "publisher": "p"}]


def _doc(collected="2026-11-04"):
    return {"collected": collected, "note": "n",
            "policy": [{"bank": "FED", "name": "FED / FOMC", "date": "2026-10-28", "decision": "HOLD", "change_bp": 0, "previous_rate": "3.75–4.00%",
                        "current_rate": "3.75–4.00%", "guidance": "neutral", "next_meeting": "2026-12-09", "sources": SRC}],
            "releases": [{"key": "us_pce", "name": "US PCE", "period": "2026-09", "date": "2026-10-29",
                          "measures": [{"key": "headline_yoy", "label": "PCE YoY", "actual": 3.6, "consensus": 3.7, "prior": 3.4}], "sources": SRC}],
            "upcoming": [{"date": "2026-11-06", "kind": "us_nfp", "name": "NFP", "sources": SRC},
                         {"date": "2026-11-13", "kind": "us_ppi_retail", "name": "PPI", "sources": SRC},
                         {"date": "2026-12-09", "kind": "fomc", "name": "FOMC", "sources": SRC}]}


def test_draft_carries_forward_without_new_values(tmp_path):
    (tmp_path / "2026-11-04.json").write_text(json.dumps(_doc()), encoding="utf-8")
    p, new = U.draft(date(2026, 11, 16), tmp_path)
    assert new and p.name == "2026-11-16.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["collected"] == "2026-11-16" and d["policy"] == _doc()["policy"] and d["releases"] == _doc()["releases"]
    # 지난 NFP 는 결과가 없어 남고(조사 대상), 판정 항목 없는 PPI 는 빠진다
    assert [u["kind"] for u in d["upcoming"]] == ["us_nfp", "fomc"]
    assert U.draft(date(2026, 11, 16), tmp_path) == (p, False)  # 이미 있으면 그대로
    p2, _ = U.draft(date(2026, 11, 17), tmp_path)
    assert json.loads(p2.read_text(encoding="utf-8"))["note"].count("이어 쓰기") == 1  # 메모가 쌓이지 않는다


def test_due_lists_past_events_without_results():
    d = _doc()
    assert U.due(d, date(2026, 11, 6)) == []  # 당일 일정은 아직 결과 전
    items = U.due(d, date(2026, 11, 10))
    assert [(x["kind"], x["target"]) for x in items] == [("us_nfp", "release")]
    d["releases"].append({"key": "us_nfp", "date": "2026-11-06"})
    assert U.due(d, date(2026, 11, 10)) == []


def test_validate_ok_and_errors():
    assert U.validate_doc(_doc(), "2026-11-04") == ([], [])
    bad = _doc()
    bad["policy"][0]["date"] = "2026-11-04"                         # 당일 결정 = look-ahead
    bad["policy"][0]["decision"] = "HIKE"; bad["policy"][0]["change_bp"] = 25  # 3.75–4.00 → 3.75–4.00 인데 +25bp
    bad["releases"][0]["sources"] = []
    bad["releases"][0]["measures"][0]["actual"] = "3.6"            # 문자열
    errs, _ = U.validate_doc(bad, "2026-11-04")
    joined = " | ".join(errs)
    for frag in ("look-ahead", "금리 산술", "출처 없음", "숫자 또는 null"):
        assert frag in joined


def test_validate_against_previous_file():
    prev = _doc("2026-11-03")
    prev["policy"].append({"bank": "BOK", "date": "2026-10-22", "decision": "HOLD", "previous_rate": "3.00%", "current_rate": "3.00%", "sources": SRC})
    errs, _ = U.validate_doc(_doc(), "2026-11-04", prev=prev)
    assert any("BOK" in e and "빠짐" in e for e in errs)


def test_fred_check_uses_release_vintage():
    calls = []

    def fetch(sid, rt):
        calls.append((sid, rt))
        if sid == "PCEPI":
            return [("2025-09-01", 100.0), ("2026-08-01", 102.9), ("2026-09-01", 103.6)]
        if sid == "DFEDTARU":
            return [("2026-10-29", 4.0)]
        raise RuntimeError("x")
    errs, warns = U.fred_check(_doc(), fetch)
    assert errs == [] and ("PCEPI", "2026-10-29") in calls
    d = _doc(); d["releases"][0]["measures"][0]["actual"] = 3.9
    errs, _ = U.fred_check(d, fetch)
    assert errs and "3.9" in errs[0]
    d = _doc(); d["releases"][0]["measures"][0]["actual"] = None    # 비운 값은 대조하지 않는다(채우지도 않는다)
    assert U.fred_check(d, fetch)[0] == []


@pytest.mark.parametrize("stem", [p.stem for p in U.files()])
def test_repo_files_pass_offline_checks(stem):
    p = U.DATA_DIR / f"{stem}.json"
    prev = U.latest_before(date.fromisoformat(stem))
    errs, _ = U.validate_doc(json.loads(p.read_text(encoding="utf-8")), stem, prev=json.loads(prev.read_text(encoding="utf-8")) if prev else None)
    assert errs == []
