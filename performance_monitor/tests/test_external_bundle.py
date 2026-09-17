"""사외 호스팅용 번들 테스트.

핵심 계약:
  - 번들을 풀면 대시보드가 읽는 스냅샷 구조 그대로여야 한다
  - 숫자가 하나도 바뀌지 않아야 한다 (번들은 옮기기만 한다)
  - anonymous 는 식별자만 바꾸고 숫자는 그대로 두어야 한다
  - 익명화 매핑은 zip 안에 들어가면 안 된다
"""
from __future__ import annotations

import zipfile

import numpy as np
import pandas as pd
import pytest

from src.data_loader import SnapshotStore
from src.external_bundle import anonymize_bundle, export_bundle


@pytest.fixture
def snapshot_dir(tmp_path, monkeypatch):
    """PM_DATA_DIR 아래에 작은 스냅샷 하나를 만든다."""
    monkeypatch.setenv("PM_DATA_DIR", str(tmp_path))
    dates = pd.DatetimeIndex(list(pd.bdate_range("2026-03-02", periods=4, tz="UTC")))
    items = ["A000001", "A000002", "A000003"]
    index = pd.MultiIndex.from_product([dates, items], names=["date", "item"])
    rng = np.random.default_rng(3)

    final_mp = pd.DataFrame(
        {"RP": rng.normal(0, .01, len(index)),
         "total_RP": rng.normal(0, .01, len(index)),
         "active_contribution_RP": rng.normal(0, .001, len(index)),
         "new_sector": ["전기전자", "금융", "화학"] * len(dates),
         "name": ["가나전자", "다라은행", "마바화학"] * len(dates)},
        index=index)
    temp_return_final = pd.DataFrame(
        {"RP": rng.normal(0, .01, len(dates)), "bm": rng.normal(0, .01, len(dates))},
        index=dates)
    betalog_final = pd.DataFrame({"RP": np.ones(len(dates))}, index=dates)
    rcf = pd.DataFrame({"RP": [.01, .009, .001]},
                       index=["total", "bm", "active"])
    info_stock = pd.DataFrame({"name": ["가나전자", "다라은행", "마바화학"]},
                              index=pd.Index(items, name="item"))

    manifest = {"as_of": "2026-03-05", "analysis_bm": "KOSPI200",
                "mp_end_date": "2026-03-05", "report_start_date": "2026-03-02",
                "mp_start_date": "2026-03-02", "models": ["RP"],
                "top_model_column": "RP", "source": "test"}
    store = SnapshotStore.create(tmp_path / "processed", "2026-03-05", manifest)
    store.write_table("final_mp", final_mp)
    store.write_table("temp_return_final", temp_return_final)
    store.write_table("betalog_final", betalog_final)
    store.write_table("return_contribution_final", rcf)
    store.write_table("info_stock", info_stock)
    store.write_json("anchors", {"WTD": "2026-03-02"})
    return tmp_path


def _extract(archive_path, target):
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(target)
    directories = sorted((target / "data" / "processed").iterdir())
    assert directories, "번들 안에 스냅샷 폴더가 없다"
    return SnapshotStore(directories[0])


# ---------------------------------------------------------------------------
# 구조와 숫자
# ---------------------------------------------------------------------------
def test_bundle_round_trips_into_a_readable_snapshot(snapshot_dir, tmp_path):
    """번들을 풀면 대시보드가 그대로 읽을 수 있어야 한다."""
    archive = export_bundle()
    restored = _extract(archive, tmp_path / "unpacked").load_all()
    original = SnapshotStore(sorted((snapshot_dir / "processed").iterdir())[0]).load_all()

    assert restored["manifest"]["as_of"] == original["manifest"]["as_of"]
    for name in ("final_mp", "temp_return_final", "betalog_final",
                 "return_contribution_final"):
        pd.testing.assert_frame_equal(restored[name], original[name])


def test_bundle_keeps_numbers_untouched(snapshot_dir, tmp_path):
    """번들은 옮기기만 한다. 숫자를 건드리면 안 된다."""
    original = SnapshotStore(sorted((snapshot_dir / "processed").iterdir())[0]).load_all()
    archive = export_bundle()
    restored = _extract(archive, tmp_path / "unpacked").load_all()
    before = float(original["return_contribution_final"].loc["active", "RP"])
    after = float(restored["return_contribution_final"].loc["active", "RP"])
    assert after == before


def test_unknown_level_is_rejected(snapshot_dir):
    with pytest.raises(ValueError, match="level"):
        export_bundle(level="somethingelse")


# ---------------------------------------------------------------------------
# 익명화
# ---------------------------------------------------------------------------
def test_anonymous_replaces_identifiers_but_not_numbers(snapshot_dir, tmp_path):
    original = SnapshotStore(sorted((snapshot_dir / "processed").iterdir())[0]).load_all()
    archive = export_bundle(level="anonymous")
    restored = _extract(archive, tmp_path / "unpacked").load_all()

    items = set(str(v) for v in
                restored["final_mp"].index.get_level_values(1).unique())
    assert items == {"STOCK_0001", "STOCK_0002", "STOCK_0003"}
    assert "name" not in restored["final_mp"].columns

    # 숫자는 그대로 (정렬 순서만 맞춰 비교)
    left = original["final_mp"]["active_contribution_RP"].to_numpy()
    right = restored["final_mp"]["active_contribution_RP"].to_numpy()
    assert np.allclose(np.sort(left), np.sort(right))


def test_anonymous_bundle_does_not_contain_the_mapping(snapshot_dir, tmp_path):
    """매핑이 zip 에 들어가면 익명화가 무의미하다."""
    archive = export_bundle(level="anonymous")
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        blob = b"".join(zf.read(n) for n in names)
    assert not any("mapping" in n for n in names)
    assert b"A000001" not in blob
    assert "가나전자".encode("utf-8") not in blob


def test_mapping_is_kept_locally(snapshot_dir):
    export_bundle(level="anonymous")
    mappings = list((snapshot_dir / "bundles").glob("mapping_*.json"))
    assert mappings, "내부 대조용 매핑이 없다"


def test_anonymize_is_stable_for_the_same_input(snapshot_dir):
    store = SnapshotStore(sorted((snapshot_dir / "processed").iterdir())[0])
    first, map_a = anonymize_bundle(store.load_all())
    second, map_b = anonymize_bundle(store.load_all())
    assert map_a == map_b
    pd.testing.assert_frame_equal(first["final_mp"], second["final_mp"])
