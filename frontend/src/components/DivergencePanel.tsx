import type { Divergence, DivergenceType, SeverityBand } from "../api/types";
import { Pending } from "./Panel";

const BAND_COLOR: Record<SeverityBand, string> = {
  CRITICAL: "var(--crit)",
  HIGH: "var(--warn)",
  MEDIUM: "var(--info)",
  LOW: "var(--faint)",
};

const TYPE_LABEL: Record<DivergenceType, string> = {
  NEWS_VS_PRICE: "뉴스 ↔ 가격",
  NEWS_VS_FLOW: "뉴스 ↔ 수급",
  PRICE_VS_FLOW: "가격 ↔ 수급",
  THEME_VS_ASSET: "테마 ↔ 자산",
  RISK_VS_VOL: "리스크 ↔ 변동성",
  OIL_VS_INFLATION_EXP: "유가 ↔ 기대인플레",
  BREADTH_VS_INDEX: "시장폭 ↔ 지수",
  CORRELATION_REGIME: "상관 레짐",
};

/**
 * 요구 7 의 [DIVERGENCE]. 이 프로젝트의 핵심 차별화 기능이다.
 *
 * 설명 문장은 백엔드가 템플릿으로 만든다. LLM 없이도 문장이 나와야 하고,
 * P3 에서 LLM 주석이 붙어도 이 문장은 남는다.
 */
export function DivergencePanel({
  items,
  themeNames,
}: {
  items: Divergence[];
  themeNames: Record<string, string>;
}) {
  if (items.length === 0) {
    return (
      <Pending stage="관측 중">
        지속 조건을 충족한 괴리가 없습니다. 한 틱만 나타난 격차는 노이즈와
        구분되지 않아 표시하지 않습니다. 두 틱 이상 이어져야 올라옵니다.
      </Pending>
    );
  }

  return (
    <div className="rows">
      {items.map((d) => (
        <article key={d.id} className="row" style={{ gridTemplateColumns: "1fr", gap: 7 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 9, flexWrap: "wrap" }}>
            <span
              className="badge"
              style={{ color: BAND_COLOR[d.severity_band], fontSize: 9.5, padding: "1px 6px" }}
            >
              {d.severity_band}
            </span>
            <span style={{ color: "var(--ink)", fontSize: 13 }}>
              {d.related_theme
                ? (themeNames[d.related_theme] ?? d.related_theme)
                : TYPE_LABEL[d.type]}
            </span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--faint)" }}>
              {TYPE_LABEL[d.type]}
            </span>
            <span
              className="num"
              style={{ marginLeft: "auto", fontSize: 11, color: "var(--muted)" }}
              title={`severity ${d.severity.toFixed(1)} · gap ${d.gap.toFixed(1)} · ${d.duration_periods}틱 지속`}
            >
              {d.severity.toFixed(0)} · {d.duration_periods}틱
            </span>
          </div>

          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            {d.legs.map((leg) => (
              <span key={leg.name} style={{ display: "flex", gap: 6, alignItems: "baseline" }}>
                <span style={{ fontSize: 11, color: "var(--faint)" }}>{leg.name}</span>
                <span className={`num ${leg.direction}`} style={{ fontSize: 12 }}>
                  {leg.value >= 0 ? "+" : ""}
                  {leg.value.toFixed(0)}
                </span>
              </span>
            ))}
          </div>

          <p style={{ margin: 0, fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.5 }}>
            {d.explanation}
          </p>
        </article>
      ))}
    </div>
  );
}
