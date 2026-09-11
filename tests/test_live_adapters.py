"""
LIVE 어댑터 계약 테스트 (설계서 STEP 7.1 대응).

**이 환경에서는 마켓데이터 호스트가 전부 차단되어 있다.** 실측이다 —
프록시가 CONNECT 를 403 으로 거부한다. 그래서 통합 테스트 대신 고정
응답 fixture 로 계약을 고정한다. 설계서가 처음부터 이 방법을 적어 두었다.

여기서 검증하는 것은 셋이다.
  1. 각 공급자가 자기 포맷을 정확히 파싱하는가
  2. 실패했을 때 조용히 0 을 채우지 않고 실패라고 말하는가
  3. 공급자 하나가 죽어도 다음 공급자로 넘어가는가

네트워크를 쓰지 않는다. 전부 바이트 문자열과 가짜 클라이언트로 돈다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from marketpulse.adapters.http import FetchError, HttpClient
from marketpulse.adapters.market.live import MIN_POINTS, LiveMarketAdapter, load_sources
from marketpulse.adapters.market.providers import (
    CsvProvider,
    FredProvider,
    StooqProvider,
    YahooProvider,
)
from marketpulse.adapters.news.rss import RssNewsAdapter, parse_feed
from marketpulse.config.registry import get_instruments
from marketpulse.models.common import DataMode

FIXTURES = Path(__file__).parent / "fixtures"
AS_OF = datetime(2026, 1, 8, tzinfo=timezone.utc)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FakeClient(HttpClient):
    """정해진 응답만 돌려주는 클라이언트. 네트워크를 쓰지 않는다."""

    def __init__(self, responses: dict[str, bytes | Exception]) -> None:
        super().__init__()
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url, *, params=None, headers=None, data=None):  # type: ignore[override]
        self.calls.append(url)
        for key, value in self.responses.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise FetchError(f"fixture 없음: {url}", kind="missing", permanent=True)


# ══════════════════════════════════════════════════════════════
class TestYahoo:
    def test_parses_closes(self):
        points = YahooProvider.parse(fixture("yahoo_spx.json"), bars=10)
        # null 종가 하나는 버린다. 0 으로 채우지 않는다.
        assert len(points) == 4
        assert points[0][1] == pytest.approx(5820.11)
        assert points[-1][1] == pytest.approx(5870.30)

    def test_timestamps_are_utc_and_ascending(self):
        points = YahooProvider.parse(fixture("yahoo_spx.json"), bars=10)
        stamps = [t for t, _ in points]
        assert stamps == sorted(stamps)
        assert all(t.tzinfo is timezone.utc for t in stamps)

    def test_scale_converts_rate_symbols(self):
        """^TNX 는 4.2% 를 42 로 준다. sources.yaml 의 scale 이 되돌린다."""
        points = YahooProvider.parse(fixture("yahoo_spx.json"), bars=10, scale=0.1)
        assert points[0][1] == pytest.approx(582.011)

    def test_api_error_raises(self):
        with pytest.raises(FetchError) as exc:
            YahooProvider.parse(fixture("yahoo_error.json"), bars=10)
        assert exc.value.permanent
        assert "delisted" in str(exc.value)

    def test_html_instead_of_json_raises(self):
        with pytest.raises(FetchError):
            YahooProvider.parse(b"<html>blocked</html>", bars=10)


class TestStooq:
    def test_parses_csv(self):
        points = StooqProvider.parse(fixture("stooq_spy.csv"), bars=10)
        assert len(points) == 3
        assert points[-1][1] == pytest.approx(590.1)

    def test_html_response_raises(self):
        """차단 페이지가 200 으로 오는 일이 흔하다. CSV 가 아니면 실패다."""
        with pytest.raises(FetchError):
            StooqProvider.parse(b"<html><body>blocked</body></html>", bars=10)


class TestFred:
    def test_skips_holiday_dots(self):
        """
        FRED 는 휴일을 "." 로 준다. 결측이지 0 이 아니다. 0 으로 읽으면
        금리가 4.21 에서 0 으로 떨어진 것이 되어 z-score 가 폭발한다.
        """
        points = FredProvider.parse(fixture("fred_dgs10.json"), bars=10)
        assert len(points) == 3
        assert all(v > 4.0 for _, v in points)

    def test_missing_key_is_reported_not_guessed(self):
        provider = FredProvider(HttpClient(), api_key=None)
        ok, why = provider.available()
        assert not ok
        assert "FRED_API_KEY" in why
        with pytest.raises(FetchError) as exc:
            provider.fetch({"symbol": "DGS10"}, bars=30, as_of=AS_OF)
        assert exc.value.permanent


class TestCsvReplay:
    def test_reads_local_file(self, tmp_path):
        (tmp_path / "US10Y.csv").write_bytes(fixture("replay_us10y.csv"))
        provider = CsvProvider(tmp_path)
        points = provider.fetch({"symbol": "US10Y"}, bars=100, as_of=AS_OF)
        assert len(points) == 40
        assert points[0][1] == pytest.approx(4.20)

    def test_korean_headers_accepted(self, tmp_path):
        (tmp_path / "X.csv").write_text("일자,종가\n2026-01-02,1380\n2026-01-03,1385\n")
        points = CsvProvider(tmp_path).fetch({"symbol": "X"}, bars=10, as_of=AS_OF)
        assert [v for _, v in points] == [1380.0, 1385.0]

    def test_missing_file_is_permanent_failure(self, tmp_path):
        with pytest.raises(FetchError) as exc:
            CsvProvider(tmp_path).fetch({"symbol": "NOPE"}, bars=10, as_of=AS_OF)
        assert exc.value.permanent

    def test_wrong_columns_say_what_was_expected(self, tmp_path):
        (tmp_path / "Y.csv").write_text("a,b\n1,2\n")
        with pytest.raises(FetchError) as exc:
            CsvProvider(tmp_path).fetch({"symbol": "Y"}, bars=10, as_of=AS_OF)
        assert "받은 열" in str(exc.value)

    @pytest.mark.parametrize(
        "name,raw,expected",
        [
            # FRED 는 값 열 이름이 심볼이다. 열이 둘뿐이면 두 번째가 값이다.
            ("fred", "observation_date,DGS10\n2026-01-02,4.21\n2026-01-06,4.26\n", [4.21, 4.26]),
            # Yahoo 다운로드 CSV. Close 를 고른다 — Open 을 고르면 사고다.
            (
                "yahoo",
                "Date,Open,High,Low,Close,Adj Close,Volume\n"
                "2026-01-02,1,2,3,5820.11,5820.11,100\n",
                [5820.11],
            ),
            # 자릿수 쉼표는 따옴표 안에 온다
            ("investing", 'Date,Price,Open\n2026-01-02,"1,380.5",1378\n', [1380.5]),
            # 퍼센트 표기로 내보내는 곳이 있다
            ("percent", "date,value\n2026-01-02,4.21%\n", [4.21]),
        ],
    )
    def test_real_world_exports_parse(self, tmp_path, name, raw, expected):
        """
        사람이 실제로 내려받는 파일이 그대로 들어가야 한다. 열 이름을 손으로
        고치게 만들면 그 과정에서 Open 을 종가로 넣는 사고가 난다.
        """
        (tmp_path / f"{name}.csv").write_text(raw)
        points = CsvProvider(tmp_path).fetch({"symbol": name}, bars=10, as_of=AS_OF)
        assert [v for _, v in points] == pytest.approx(expected)

    def test_ambiguous_wide_file_is_refused_not_guessed(self, tmp_path):
        """
        열이 여럿인데 알려진 이름이 없으면 거부한다. 짐작해서 고르면
        Open 을 종가로 읽는다 — 조용히 틀린 값이 화면에 오른다.
        """
        (tmp_path / "W.csv").write_text("date,a,b\n2026-01-02,1,2\n")
        with pytest.raises(FetchError):
            CsvProvider(tmp_path).fetch({"symbol": "W"}, bars=10, as_of=AS_OF)

    def test_fred_holiday_dot_is_missing_not_zero(self, tmp_path):
        """
        "." 를 0 으로 읽으면 금리가 4.21 에서 0 으로 떨어진 것이 되어
        z-score 가 폭발한다.
        """
        (tmp_path / "R.csv").write_text(
            "observation_date,DGS10\n2026-01-02,4.21\n2026-01-03,.\n2026-01-06,4.26\n"
        )
        points = CsvProvider(tmp_path).fetch({"symbol": "R"}, bars=10, as_of=AS_OF)
        assert len(points) == 2

    def test_cp949_export_is_read(self, tmp_path):
        """KRX·네이버에서 받은 파일은 대개 CP949 다."""
        (tmp_path / "K.csv").write_bytes("일자,종가\n2026-01-02,\"2,540.10\"\n".encode("cp949"))
        points = CsvProvider(tmp_path).fetch({"symbol": "K"}, bars=10, as_of=AS_OF)
        assert [v for _, v in points] == pytest.approx([2540.10])


# ══════════════════════════════════════════════════════════════
class TestSourcesConfig:
    def test_every_id_exists_in_the_registry(self):
        """끊어진 참조가 있으면 영영 안 불리는 설정이 남는다."""
        known = {i.id for i in get_instruments().instruments}
        for iid in load_sources():
            assert iid in known, iid

    def test_no_source_for_derived_instruments(self):
        """파생 지표는 기초 자산에서 계산한다. 따로 받아오면 두 값이 어긋난다."""
        derived = {
            i.id for i in get_instruments().instruments if i.derived_from is not None
        }
        assert derived
        assert not (derived & set(load_sources()))

    def test_every_provider_name_is_implemented(self, tmp_path):
        adapter = LiveMarketAdapter(replay_dir=tmp_path)
        for iid, plan in load_sources().items():
            for spec in plan:
                assert spec["provider"] in adapter.providers, f"{iid}: {spec}"

    def test_instruments_without_a_free_provider_are_explicit(self):
        """
        breadth 계열은 무료 공급자가 없다. 빈 목록으로 **명시**되어 있어야
        한다 — 설정에서 빠진 것과 "받을 곳이 없다" 는 다르다.
        """
        sources = load_sources()
        for iid in ("KOSPI_ADV_RATIO", "KOSPI_NHNL", "SPX_ADV_RATIO"):
            assert iid in sources
            assert sources[iid] == []


class TestFallbackChain:
    @pytest.fixture
    def instruments(self):
        by_id = get_instruments().by_id()
        return [by_id["SPX"]]

    def test_falls_through_to_the_next_provider(self, instruments, tmp_path):
        """Yahoo 가 죽으면 stooq 로 넘어간다. 한 공급자의 장애가 끝이 아니다."""
        client = FakeClient(
            {
                "finance.yahoo.com": FetchError("차단됨", kind="network"),
                "stooq.com": fixture("stooq_spy.csv") * 10,
            }
        )
        adapter = LiveMarketAdapter(replay_dir=tmp_path, client=client)
        adapter.fetch_series(instruments, bars=30, as_of=AS_OF)
        outcome = adapter.outcomes["SPX"]
        # stooq fixture 는 3행뿐이라 MIN_POINTS 에 못 미친다. 그래도
        # "시도했고 왜 실패했는지" 가 남아야 한다.
        assert [name for name, _ in outcome.attempts] == ["yahoo", "stooq"]

    def test_short_series_is_rejected_not_used(self, instruments, tmp_path):
        """20개 미만이면 z-score 의 분모가 잡음이다. 쓰지 않는다."""
        client = FakeClient({"finance.yahoo.com": fixture("yahoo_spx.json")})
        adapter = LiveMarketAdapter(replay_dir=tmp_path, client=client)
        series = adapter.fetch_series(instruments, bars=30, as_of=AS_OF)
        assert series == {}
        assert str(MIN_POINTS) in adapter.outcomes["SPX"].reason

    def test_local_csv_is_always_the_last_resort(self, tmp_path):
        """
        네트워크가 전부 막혀도 파일을 넣어 두면 살아난다. sources.yaml 을
        고칠 필요가 없다 — 막힌 환경의 탈출구다.
        """
        (tmp_path / "US10Y.csv").write_bytes(fixture("replay_us10y.csv"))
        by_id = get_instruments().by_id()
        client = FakeClient({"": FetchError("전부 차단", kind="network")})
        adapter = LiveMarketAdapter(replay_dir=tmp_path, client=client)
        series = adapter.fetch_series([by_id["US10Y"]], bars=100, as_of=AS_OF)
        assert "US10Y" in series
        assert adapter.outcomes["US10Y"].provider == "csv"

    def test_provenance_travels_with_the_data(self, tmp_path):
        """어디서 온 값인지 화면에서 볼 수 있어야 한다 (요구 15-6)."""
        (tmp_path / "US10Y.csv").write_bytes(fixture("replay_us10y.csv"))
        by_id = get_instruments().by_id()
        adapter = LiveMarketAdapter(replay_dir=tmp_path, client=FakeClient({}))
        series = adapter.fetch_series([by_id["US10Y"]], bars=100, as_of=AS_OF)
        assert series["US10Y"].meta.source == "csv:US10Y"
        assert series["US10Y"].meta.mode is DataMode.DELAYED

    def test_total_failure_yields_nothing_not_zeros(self, instruments, tmp_path):
        """
        전부 실패하면 그 종목은 빠진다. 0 으로 채우면 "가격이 0 이 됐다" 는
        뜻이 되어 z-score 가 폭발한다 (개발 규칙 3).
        """
        client = FakeClient({"": FetchError("차단", kind="network")})
        adapter = LiveMarketAdapter(replay_dir=tmp_path, client=client)
        assert adapter.fetch_series(instruments, bars=30, as_of=AS_OF) == {}
        assert not adapter.outcomes["SPX"].ok

    def test_derived_needs_both_legs(self, tmp_path):
        by_id = get_instruments().by_id()
        adapter = LiveMarketAdapter(replay_dir=tmp_path, client=FakeClient({}))
        adapter.fetch_series(
            [by_id["US2Y"], by_id["US10Y"], by_id["CURVE_2S10S"]], bars=30, as_of=AS_OF
        )
        outcome = adapter.outcomes["CURVE_2S10S"]
        assert not outcome.ok
        assert "기초 자산 누락" in outcome.reason


# ══════════════════════════════════════════════════════════════
class TestRss:
    def test_parses_items(self):
        items = parse_feed(fixture("rss_sample.xml"), source="테스트", weight=1.0, lang="ko")
        assert len(items) == 3
        assert items[0].title.startswith("기대인플레이션")
        # description 의 HTML 태그는 벗긴다
        assert "<p>" not in items[0].body

    def test_timezone_is_normalised(self):
        items = parse_feed(fixture("rss_sample.xml"), source="테스트", weight=1.0, lang="ko")
        assert all(i.published_at.tzinfo is not None for i in items)

    def test_ids_are_stable(self):
        """같은 기사가 매 틱 새 id 를 받으면 중복 제거가 무너진다."""
        a = parse_feed(fixture("rss_sample.xml"), source="t", weight=1.0, lang="ko")
        b = parse_feed(fixture("rss_sample.xml"), source="t", weight=1.0, lang="ko")
        assert [i.id for i in a] == [i.id for i in b]

    def test_different_sources_give_different_ids(self):
        a = parse_feed(fixture("rss_sample.xml"), source="A", weight=1.0, lang="ko")
        b = parse_feed(fixture("rss_sample.xml"), source="B", weight=1.0, lang="ko")
        assert {i.id for i in a}.isdisjoint({i.id for i in b})

    def test_garbage_raises(self):
        with pytest.raises(FetchError):
            parse_feed(b"not xml at all", source="t", weight=1.0, lang="ko")

    def test_future_dated_items_are_dropped(self, tmp_path):
        """
        피드가 타임존을 틀리는 일이 흔하다. 미래 기사를 그대로 두면 시간
        감쇠 가중이 1 을 넘어 그 기사가 전체를 지배한다.
        """
        feeds = tmp_path / "feeds.yaml"
        feeds.write_text(
            "feeds:\n  - {name: 테스트, url: 'https://example.test/f.xml', lang: ko}\n"
        )
        adapter = RssNewsAdapter(
            config_dir=tmp_path,
            client=FakeClient({"example.test": fixture("rss_sample.xml")}),
        )
        items = adapter.fetch_news(as_of=AS_OF)
        assert len(items) == 2
        assert all(i.published_at <= AS_OF for i in items)

    def test_dead_feed_does_not_kill_the_rest(self, tmp_path):
        feeds = tmp_path / "feeds.yaml"
        feeds.write_text(
            "feeds:\n"
            "  - {name: 죽은피드, url: 'https://dead.test/f.xml', lang: ko}\n"
            "  - {name: 산피드, url: 'https://alive.test/f.xml', lang: ko}\n"
        )
        adapter = RssNewsAdapter(
            config_dir=tmp_path,
            client=FakeClient(
                {
                    "dead.test": FetchError("차단", kind="network"),
                    "alive.test": fixture("rss_sample.xml"),
                }
            ),
        )
        items = adapter.fetch_news(as_of=AS_OF)
        assert items
        assert "차단" in adapter.outcomes["죽은피드"]
        assert adapter.outcomes["산피드"].endswith("건")

    def test_duplicate_headlines_collapse(self, tmp_path):
        """같은 기사가 여러 피드에 실린다. 세 번 세면 감성 가중이 틀어진다."""
        feeds = tmp_path / "feeds.yaml"
        feeds.write_text(
            "feeds:\n"
            "  - {name: A, url: 'https://a.test/f.xml', lang: ko}\n"
            "  - {name: B, url: 'https://b.test/f.xml', lang: ko}\n"
        )
        adapter = RssNewsAdapter(
            config_dir=tmp_path,
            client=FakeClient(
                {"a.test": fixture("rss_sample.xml"), "b.test": fixture("rss_sample.xml")}
            ),
        )
        assert len(adapter.fetch_news(as_of=AS_OF)) == 2


# ══════════════════════════════════════════════════════════════
class TestCircuitBreaker:
    def test_opens_after_repeated_failures(self):
        """
        죽은 공급자를 매 틱 두드리는 것은 지연만 늘린다. LLM 클라이언트와
        같은 구조다.
        """
        client = HttpClient(retries=0, timeout_sec=0.01)
        host = "https://blocked.invalid/x"
        for _ in range(3):
            with pytest.raises(FetchError):
                client.get(host)
        with pytest.raises(FetchError) as exc:
            client.get(host)
        assert exc.value.kind == "circuit"
        assert "차단" in client.status()["blocked.invalid"]


class TestReplayDoc:
    """
    CSV 적재 안내가 레지스트리와 어긋나면 사용자가 없는 종목을 채우거나
    있는 종목을 빠뜨린다. 문서도 계약이다.
    """

    @pytest.fixture(scope="class")
    def doc(self):
        return (
            Path(__file__).resolve().parents[1]
            / "marketpulse" / "data" / "replay" / "README.md"
        ).read_text(encoding="utf-8")

    def test_every_instrument_is_documented(self, doc):
        import re

        ids = {i.id for i in get_instruments().instruments}
        mentioned = {m for m in re.findall(r"`([A-Z][A-Z0-9_]{1,24})`", doc) if m in ids}
        assert ids - mentioned == set(), f"문서에 없는 종목: {sorted(ids - mentioned)}"

    def test_derived_are_marked_as_do_not_fill(self, doc):
        derived = [
            i.id for i in get_instruments().instruments if i.derived_from is not None
        ]
        section = doc[doc.index("넣으면 안 되는 것") :]
        for iid in derived:
            assert iid in section, iid

    def test_unit_conversion_warnings_are_present(self, doc):
        """
        단위를 틀리면 조용히 틀린 값이 화면에 오른다. US_HY_OAS 의 bp 변환과
        수급의 십억원 변환은 반드시 적혀 있어야 한다.
        """
        assert "×100" in doc or "x100" in doc
        assert "십억원" in doc
