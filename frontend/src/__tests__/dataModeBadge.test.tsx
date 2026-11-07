/** 배지의 나이는 거래일로 센다 — 금요일 봉을 월요일에 '3일 전' 이라 부르지 않는다. */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { DataHealth } from "../api/types";
import { DataModeBadge, freshness } from "../components/DataModeBadge";

const base: DataHealth = {
  mode: "DELAYED", coverage: 0.74, expected_instruments: 50, available_instruments: 37, missing: [], stale: ["US10Y"],
  max_freshness_sec: 348278, max_freshness_trading_days: 2, oldest_instruments: ["US10Y", "US2Y"],
  freshness_note: "가장 오래된 재료는 2거래일 전 봉이다 (주말 제외, 각 시장 휴장일은 반영하지 않아 실제 거래일 수의 상한). 해당 계열: US10Y, US2Y.",
  news_items: 0, llm_status: "disabled", news_judgment: "manual", news_judgment_note: "수기", engine_timings_ms: {}, warnings: [],
};

describe("DataModeBadge freshness", () => {
  it("하루 이상 지난 재료는 거래일로 센다 (4일 전 → 2거래일 전)", () => {
    render(<DataModeBadge health={base} scenario={null} />);
    const el = screen.getByTestId("freshness");
    expect(el.textContent).toBe("2거래일 전");
    expect(el.getAttribute("title")).toContain("초로는 4일 전");
    expect(el.getAttribute("title")).toContain("US10Y, US2Y");
  });

  it("같은 거래일 안이면 초·분·시간, 옛 캡처(필드 없음)는 초 기준", () => {
    expect(freshness({ max_freshness_sec: 5400, max_freshness_trading_days: 0 })).toBe("1시간 전");
    expect(freshness({ max_freshness_sec: 45 })).toBe("45초 전");
    expect(freshness({ max_freshness_sec: 348278 })).toBe("4일 전");
  });
});
