import { useState } from "react";
import type { AltDataPoint } from "../api/investment";
import { Empty, QUALITY, pct, sig, zGapTag } from "../investment/fmt";

const GROUP_LABEL: Record<string, string> = {
  semiconductor: "반도체", energy: "에너지", metals: "금속", chemicals: "화학", agriculture: "농산물",
  shipping: "해운·물류", china: "중국", peer: "글로벌 peer", market: "시장",
};

/**
 * Alternative Data Pulse (2). 시세표가 아니다 — 줄마다 '왜 중요한가' 와 '누가 영향받나' 가 붙는다.
 * 데이터가 없는 항목도 줄을 남긴다. 없는 것을 감추면 "다 봤다" 는 거짓 안도감을 준다.
 */
export function AlternativeDataPulse({ points }: { points: AltDataPoint[] }) {
  const [open, setOpen] = useState<string | null>(null);
  if (points.length === 0) return <Empty>대체데이터가 정의되지 않았습니다.</Empty>;
  const groups: string[] = [];
  for (const p of points) if (!groups.includes(p.group)) groups.push(p.group);
  const moving = points.filter((p) => p.z !== null && Math.abs(p.z) >= 1.0 && p.quality !== "MISSING");

  return (
    <div className="rows">
      {moving.length > 0 && (
        <div className="ii-moving mono">
          <span className="ii-k">지금 움직이는 것</span>
          {moving.slice(0, 8).map((p) => (
            <span key={p.id} className={`ii-chip ${p.z! >= 0 ? "up" : "down"}`} title={p.why}>{p.label} {sig(p.z)}</span>
          ))}
        </div>
      )}
      <div className="row ii-alt-row ii-head mono">
        <span>지표</span><span style={{ textAlign: "right" }}>값</span><span style={{ textAlign: "right" }}>1D</span>
        <span style={{ textAlign: "right" }}>1W</span><span style={{ textAlign: "right" }}>1M</span><span style={{ textAlign: "right" }}>3M</span>
        <span style={{ textAlign: "right" }}>z</span><span>%ile</span>
      </div>
      {groups.map((g) => (
        <div key={g}>
          <div className="ii-group mono">{GROUP_LABEL[g] ?? g}</div>
          {points.filter((p) => p.group === g).map((p) => {
            const missing = p.quality === "MISSING";
            const isOpen = open === p.id;
            return (
              <div key={p.id}>
                <div
                  className={`row ii-alt-row row-toggle${missing ? " ii-missing" : ""}`}
                  role="button" tabIndex={0} aria-expanded={isOpen}
                  onClick={() => setOpen(isOpen ? null : p.id)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(isOpen ? null : p.id); } }}
                >
                  <span className="row-label">
                    <span className="mono" aria-hidden="true" style={{ color: "var(--faint)", marginRight: 6, fontSize: 9 }}>{isOpen ? "▾" : "▸"}</span>
                    {p.label}
                    {p.proxy_for ? <span className="row-sub" title={p.proxy_for}> 대리</span> : null}
                    {p.quality !== "OK" ? <span className="row-sub" style={{ color: QUALITY[p.quality].color }}> {QUALITY[p.quality].label}</span> : null}
                    {p.rollover_suspect ? <span className="row-sub" style={{ color: "var(--warn)" }} title={p.note}> 롤오버?</span> : null}
                    {zGapTag(p) ? <span className="row-sub" style={{ color: "var(--info)" }} title={p.note} data-testid="zgap"> {zGapTag(p)}</span> : null}
                  </span>
                  <span className="num" style={{ textAlign: "right" }}>{p.value === null ? "–" : p.value >= 1000 ? p.value.toLocaleString("ko-KR", { maximumFractionDigits: 0 }) : p.value.toFixed(2)}</span>
                  <span className={`num ${p.change_1d !== null && p.change_1d >= 0 ? "up" : "down"}`} style={{ textAlign: "right" }}>{pct(p.change_1d)}</span>
                  <span className="num" style={{ textAlign: "right" }}>{pct(p.change_1w, 1)}</span>
                  <span className="num" style={{ textAlign: "right" }}>{pct(p.change_1m, 1)}</span>
                  <span className="num" style={{ textAlign: "right" }}>{pct(p.change_3m, 1)}</span>
                  <span className={`num ${p.z !== null && p.z >= 0 ? "up" : "down"}`} style={{ textAlign: "right" }}>{sig(p.z)}</span>
                  <span className="mono" style={{ fontSize: 10, color: "var(--faint)" }} title={`최근 ${p.percentile_observations}봉`}>{p.percentile === null ? "–" : `${p.percentile.toFixed(0)}%`}</span>
                </div>
                {isOpen && (
                  <div className="theme-news">
                    <div className="ii-why">
                      <div><span className="ii-k">Why it matters</span> {p.why}</div>
                      <div><span className="ii-k">Affected</span> {p.affected_names.length ? p.affected_names.join(" · ") : "정의된 종목 없음"}</div>
                      {p.proxy_for && <div><span className="ii-k">대리 지표</span> {p.proxy_for}</div>}
                      <div className="ii-src mono">{p.source ?? "출처 없음"} · {p.source_type}{p.as_of ? ` · ${new Date(p.as_of).toLocaleDateString("ko-KR")}` : ""}</div>
                      {p.note && <div style={{ color: "var(--muted)" }}>{p.note}</div>}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
