"""사외 호스팅용 스냅샷 번들.

대시보드는 DB 에 붙지 않는다. **스냅샷 폴더만 읽는다.** 따라서 내부에서 계산해
만든 스냅샷을 밖으로 옮기면, 밖에서 같은 Streamlit 대시보드가 그대로 뜬다.
필터·드릴다운·메뉴 이동이 전부 동작한다.

    pm.export_bundle()                     # 최신 스냅샷을 zip 으로
    pm.export_bundle(level='anonymous')    # 종목 식별자를 가린다

**반출 자체가 승인 사항이다.** 이 도구는 무엇을 담을지 고를 수 있게 해줄 뿐,
반출해도 되는지는 정보보호팀이 정한다.

담기는 것
---------
``full``       스냅샷 전체. 종목명·보유비중·종목별 기여도가 들어 있다.
``anonymous``  종목 식별자를 STOCK_0001 형태로 바꾼다. 모든 화면이 동작한다.

**anonymous 의 한계를 분명히 한다.** 업종과 일별 수익률이 남으므로, 시장
데이터를 가진 사람은 수익률 계열을 맞춰 원 종목을 알아낼 수 있다. 일반 열람자
기준의 가림막이지 암호학적 익명화가 아니다. **실질적인 통제는 어디에 올리고
누가 접근하느냐이지 이 옵션이 아니다.**
"""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from .config import load_config
from .data_loader import SNAPSHOT_TABLES, SnapshotStore, latest_snapshot, list_snapshots

__all__ = ["export_bundle", "anonymize_bundle", "LEVELS"]

LEVELS = ("full", "anonymous")

# 종목 식별자가 들어 있는 자리
ITEM_LEVEL = 1          # final_mp 의 MultiIndex (date, item)
NAME_COLUMNS = ("name", "종목명", "stock_name", "kor_name")


def _stock_ids(bundle: dict) -> list:
    final_mp = bundle.get("final_mp")
    if final_mp is None:
        return []
    return sorted({str(v) for v in final_mp.index.get_level_values(ITEM_LEVEL)})


def anonymize_bundle(bundle: dict) -> tuple[dict, dict]:
    """종목 식별자를 STOCK_0001 형태로 바꾼다. (새 bundle, 매핑) 을 돌려준다.

    매핑은 **반출하지 않는다.** 내부에 남겨 두면 나중에 대조할 수 있다.
    """
    mapping = {code: "STOCK_%04d" % (i + 1)
               for i, code in enumerate(_stock_ids(bundle))}
    out = dict(bundle)

    final_mp = bundle.get("final_mp")
    if final_mp is not None:
        frame = final_mp.copy()
        index = frame.index
        renamed = [mapping.get(str(v), str(v))
                   for v in index.get_level_values(ITEM_LEVEL)]
        levels = [index.get_level_values(i) for i in range(index.nlevels)]
        levels[ITEM_LEVEL] = pd.Index(renamed, name=index.names[ITEM_LEVEL])
        frame.index = pd.MultiIndex.from_arrays(levels, names=index.names)
        for column in NAME_COLUMNS:
            if column in frame.columns:
                frame = frame.drop(columns=[column])
        out["final_mp"] = frame

    info = bundle.get("info_stock")
    if info is not None and len(info):
        frame = info.copy()
        frame.index = pd.Index([mapping.get(str(v), str(v)) for v in frame.index],
                               name=frame.index.name)
        for column in NAME_COLUMNS:
            if column in frame.columns:
                frame[column] = frame.index
        out["info_stock"] = frame

    manifest = dict(bundle.get("manifest", {}))
    manifest["anonymized"] = True
    manifest["source"] = str(manifest.get("source", "")) + "+anonymized"
    out["manifest"] = manifest
    return out, mapping


def export_bundle(as_of: str | None = None, level: str = "full",
                  out: str | Path | None = None,
                  keep_mapping: bool = True) -> Path:
    """사외 호스팅용 zip 을 만든다.

    Parameters
    ----------
    level         'full' 또는 'anonymous'
    keep_mapping  익명화 매핑을 내부에 남긴다 (zip 에는 넣지 않는다)
    """
    if level not in LEVELS:
        raise ValueError("level 은 %s 중 하나여야 합니다." % (LEVELS,))

    config = load_config()
    if as_of is None:
        snapshot = latest_snapshot(config)
        if snapshot is None:
            raise FileNotFoundError(
                "스냅샷이 없습니다. pm.export_snapshot(globals()) 를 먼저 실행하십시오.")
    else:
        matches = [s for s in list_snapshots(config) if s.as_of == as_of]
        if not matches:
            raise FileNotFoundError("해당 기준일 스냅샷이 없습니다: %s" % as_of)
        snapshot = matches[0]

    bundle = SnapshotStore(snapshot.path).load_all()
    mapping = {}
    if level == "anonymous":
        bundle, mapping = anonymize_bundle(bundle)

    as_of_value = bundle["manifest"].get("as_of", snapshot.as_of)
    stamp = str(as_of_value).replace("-", "")
    if out is None:
        directory = config.data_dir / "bundles"
        directory.mkdir(parents=True, exist_ok=True)
        out = directory / ("pm_bundle_%s_%s.zip" % (stamp, level))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "data" / "processed"
        store = SnapshotStore.create(staging, str(as_of_value), bundle["manifest"])
        for name, _required in SNAPSHOT_TABLES:
            frame = bundle.get(name)
            if frame is not None:
                store.write_table(name, frame)
        if bundle.get("anchors"):
            store.write_json("anchors", bundle["anchors"])
        for extra in ("notebook_params", "validation"):
            source = snapshot.path / ("%s.json" % extra)
            if source.exists() and level == "full":
                shutil.copy2(source, store.path / ("%s.json" % extra))

        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for item in sorted(Path(tmp).rglob("*")):
                if item.is_file():
                    archive.write(item, item.relative_to(tmp).as_posix())

    if mapping and keep_mapping:
        secret = config.data_dir / "bundles" / ("mapping_%s.json" % stamp)
        secret.parent.mkdir(parents=True, exist_ok=True)
        secret.write_text(json.dumps(mapping, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        try:
            import os

            os.chmod(secret, 0o600)
        except OSError:
            pass

    size = out.stat().st_size / 1024 / 1024
    print("번들 생성: %s  (%.1f MB)" % (out, size))
    print("  기준일 %s · level=%s · 종목 %d" %
          (as_of_value, level, len(_stock_ids(bundle))))
    if level == "anonymous":
        print("  종목 식별자를 STOCK_#### 로 바꿨습니다.")
        if keep_mapping:
            print("  매핑은 내부에만 남겼습니다(zip 에 없음): %s" % secret)
        print("  ※ 업종과 일별 수익률이 남으므로, 시장 데이터를 가진 사람은")
        print("     원 종목을 역추적할 수 있습니다. 일반 열람자 기준의 가림막입니다.")
    else:
        print("  ※ 종목명·보유비중·종목별 기여도가 들어 있습니다. 대외비입니다.")
    print()
    print("  사외 서버에서:")
    print("     unzip %s -d /srv/pm" % out.name)
    print("     PM_DATA_DIR=/srv/pm/data streamlit run app.py")
    print("  반출 여부는 정보보호팀 승인 사항입니다.")
    return out
