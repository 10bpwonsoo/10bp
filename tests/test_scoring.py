"""스코어링 공통 부품 테스트 (설계서 STEP 5.1)."""

from __future__ import annotations

import math

import pytest

from marketpulse.engines.scoring import (
    Component,
    parse_expression,
    renormalized_average,
    squash,
    unsquash,
    weighted_z,
)


class TestSquash:
    @pytest.mark.parametrize(
        "z,expected", [(1.0, 46.2), (2.0, 76.2), (3.0, 90.5), (0.0, 0.0)]
    )
    def test_known_points(self, z, expected):
        """설계 문서가 제시한 값과 일치해야 한다."""
        assert squash(z) == pytest.approx(expected, abs=0.1)

    def test_saturates(self):
        """
        꼬리에서 한계 증가폭이 줄어야 한다. 극단치가 전체 점수를 지배하는
        것을 막는 성질이다. 선형이었다면 두 구간의 증가폭이 같다.
        """
        near_zero = squash(2.0) - squash(0.0)
        far_tail = squash(6.0) - squash(4.0)
        assert far_tail < near_zero / 10.0

    def test_monotonic_and_odd(self):
        assert squash(1.0) < squash(2.0) < squash(3.0)
        assert squash(-2.0) == pytest.approx(-squash(2.0))

    def test_round_trip(self):
        for z in (-3.0, -0.5, 0.0, 1.25, 2.5):
            assert unsquash(squash(z)) == pytest.approx(z, abs=1e-9)

    def test_unsquash_clamps_at_bounds(self):
        assert math.isfinite(unsquash(100.0))
        assert math.isfinite(unsquash(-100.0))


class TestWeightedZ:
    def test_signed_weighting(self):
        comps = [Component("A", 0.5, 1), Component("B", 0.5, -1)]
        value, _, cov = weighted_z(comps, lambda k: 2.0, method="m")
        assert value == pytest.approx(0.0)
        assert cov == 1.0

    def test_missing_renormalizes_not_zero_fills(self):
        """
        결측을 0 으로 채우면 값이 희석된다. 분모에서 빼야 한다.
        A=2.0 하나만 있으면 결과는 1.0 이 아니라 2.0 이어야 한다.
        """
        comps = [Component("A", 0.5), Component("B", 0.5)]
        value, bd, cov = weighted_z(
            comps, lambda k: 2.0 if k == "A" else None, method="m"
        )
        assert value == pytest.approx(2.0)
        assert bd.missing_inputs == ["B"]
        assert cov == pytest.approx(0.5)

    def test_all_missing_returns_none(self):
        comps = [Component("A", 1.0)]
        value, _, cov = weighted_z(comps, lambda k: None, method="m")
        assert value is None and cov == 0.0

    def test_breakdown_records_every_contribution(self):
        comps = [Component("A", 0.35, 1), Component("B", 0.25, -1)]
        _, bd, _ = weighted_z(comps, lambda k: 2.0, method="m")
        by_key = {c.key: c for c in bd.contributions}
        assert by_key["A"].contribution == pytest.approx(0.7)
        assert by_key["B"].contribution == pytest.approx(-0.5)
        assert bd.inputs_hash


class TestExpressions:
    @pytest.mark.parametrize(
        "raw,kind,name,absolute",
        [
            ("Inflation >= 1.0", "factor", "Inflation", False),
            ("z(BRENT) >= 1.0", "instrument", "BRENT", False),
            ("abs(Rates) >= 1.2", "factor", "Rates", True),
            ("abs(z(GOLD)) <= 0.5", "instrument", "GOLD", True),
        ],
    )
    def test_parse(self, raw, kind, name, absolute):
        e = parse_expression(raw)
        assert (e.kind, e.name, e.absolute) == (kind, name, absolute)

    @pytest.mark.parametrize(
        "raw",
        [
            "__import__('os').system('rm -rf /') >= 1",
            "Inflation",
            "Inflation >= abc",
            "1 + 1 >= 2",
            "",
        ],
    )
    def test_rejects_anything_not_allowed(self, raw):
        """설정 파일이 임의 코드를 실행할 수 있으면 그건 설정이 아니라 코드다."""
        with pytest.raises(ValueError):
            parse_expression(raw)

    def test_evaluate(self):
        e = parse_expression("Inflation >= 1.0")
        assert e.evaluate(lambda k, n: 1.7) == (True, 1.7)
        assert e.evaluate(lambda k, n: 0.4) == (False, 0.4)

    def test_absolute(self):
        e = parse_expression("abs(Rates) >= 1.2")
        assert e.evaluate(lambda k, n: -1.5)[0] is True
        assert e.evaluate(lambda k, n: -1.5)[1] == 1.5

    def test_missing_value_is_not_a_pass(self):
        """평가 불가를 통과로 처리하면 데이터가 없을수록 라벨이 잘 붙는다."""
        e = parse_expression("Inflation >= 1.0")
        assert e.evaluate(lambda k, n: None) == (False, None)


class TestRenormalizedAverage:
    def test_unknown_excluded_from_denominator(self):
        value, unknown = renormalized_average(
            {"a": 1.0, "b": None}, {"a": 0.6, "b": 0.4}
        )
        assert value == pytest.approx(1.0)
        assert unknown == ["b"]

    def test_all_unknown_returns_none(self):
        value, unknown = renormalized_average({"a": None}, {"a": 1.0})
        assert value is None and unknown == ["a"]
