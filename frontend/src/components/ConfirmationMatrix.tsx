import type { ThemeState } from "../api/types";
import { Pending } from "./Panel";
import { SignalBar } from "./SignalBar";

/**
 * 요구 10 의 [FLOW & PRICE CONFIRMATION].
 *
 * News · Flow · Price · Volatility 네 신호를 나란히 놓는다. 서로를 확인하는지
 * 한눈에 보는 것이 목적이라 숫자보다 방향과 크기를 먼저 읽히게 했다.
 */
const VERDICT: Record<ThemeState["cross_asset_confirmation"], { label: string; color: string }> = {
  HIGH: { label: "일치", color: "var(--ok)" },
  MEDIUM: { label: "보통", color: "var(--muted)" },
  LOW: { label: "약함", color: "var(--faint)" },
  CONFLICT: { label: "상충", color: "var(--crit)" },
};

export function ConfirmationMatrix({ themes }: { themes: ThemeState[] }) {
  const ranked = [...themes]
    .filter((t) => t.confirmation_score !== null)
    .sort((a, b) => Math.abs(b.theme_score) - Math.abs(a.theme_score))
    .slice(0, 7);

  if (ranked.length === 0) {
    return (
      <Pending stage="P2">
        네 신호를 비교할 만큼 유효한 테마가 없습니다. 각 테마에 최소 두 개의
        신호가 측정되어야 확인을 시도합니다.
      </Pending>
    );
  }

  const columns: Array<[string, keyof ThemeState]> = [
    ["News", "news_sentiment"],
    ["Price", "price_momentum"],
    ["Flow", "flow_momentum"],
    ["Vol", "volatility"],
  ];

  return (
    <div className="rows">
      <div
        className="row"
        style={{
          gridTemplateColumns: "minmax(0,1.1fr) repeat(4, 1fr) 48px",
          color: "var(--faint)",
          fontSize: 10,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          fontFamily: "var(--font-mono)",
        }}
      >
        <span>테마</span>
        {columns.map(([label]) => (
          <span key={label}>{label}</span>
        ))}
        <span style={{ textAlign: "right" }}>확인</span>
      </div>

      {ranked.map((t) => {
        const verdict = VERDICT[t.cross_asset_confirmation];
        return (
          <div
            key={t.theme_id}
            className="row"
            style={{ gridTemplateColumns: "minmax(0,1.1fr) repeat(4, 1fr) 48px" }}
          >
            <span className="row-label">{t.name}</span>
            {columns.map(([label, field]) => {
              const v = t[field] as number | null;
              return (
                <span
                  key={label}
                  title={v === null ? `${label}: 측정되지 않음` : `${label} ${v.toFixed(0)}`}
                  style={{ display: "flex", flexDirection: "column", gap: 2 }}
                >
                  <SignalBar value={v} />
                  <span
                    className="num"
                    style={{
                      fontSize: 10,
                      color: v === null ? "var(--faint)" : "var(--muted)",
                    }}
                  >
                    {v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(0)}`}
                  </span>
                </span>
              );
            })}
            <span
              className="mono"
              style={{ textAlign: "right", fontSize: 10.5, color: verdict.color }}
            >
              {verdict.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
