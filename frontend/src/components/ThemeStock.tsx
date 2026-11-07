import type { ThemeStockRow } from "../api/investment";
import { AGREEMENT, Empty, num, pct, sig } from "../investment/fmt";

/** Theme → Stock (7). 기존 테마 점수가 실제 종목에서 확인되는가. */
export function ThemeStock({ rows }: { rows: ThemeStockRow[] }) {
  if (rows.length === 0) return <Empty>테마에 매핑된 종목이 없습니다.</Empty>;
  return (
    <div className="rows">
      {rows.map((t) => (
        <div key={t.theme_id} className="row" style={{ gridTemplateColumns: "minmax(0,1fr)", gap: 4 }}>
          <div style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
            <span style={{ color: "var(--ink)" }}>{t.theme_name}</span>
            <span className={`num ${t.theme_score >= 0 ? "up" : "down"}`}>{num(t.theme_score)}</span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--faint)" }}>뉴스 {num(t.news_sentiment)}</span>
            <span className="mono" style={{ fontSize: 10.5, color: AGREEMENT[t.agreement].color, marginLeft: "auto" }}>종목 {AGREEMENT[t.agreement].label}</span>
          </div>
          <div className="ii-links">
            {t.stocks.slice(0, 6).map((s) => (
              <span key={s.stock_id} className={`ii-chip ${s.z !== null && s.z >= 0 ? "up" : "down"}`} title={`1D ${pct(s.change_1d)} · 1W ${pct(s.change_1w, 1)}`}>
                {s.name} <span className="num">{sig(s.z)}</span>
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
