import type { SemiconductorIntelligence as Semi } from "../api/investment";
import { Empty, MiniBar, QUALITY, pct, sig } from "../investment/fmt";

function dirWord(d: number | null) {
  if (d === null) return { t: "판단 불가", c: "var(--faint)" };
  if (d >= 0.5) return { t: "상승", c: "var(--up)" };
  if (d <= -0.5) return { t: "하락", c: "var(--down)" };
  return { t: "혼조", c: "var(--muted)" };
}

/** Semiconductor Intelligence (4). 메모리 가격 · 글로벌 peer · 국내 · EPS 가 같은 방향인가. */
export function SemiconductorIntelligence({ s }: { s: Semi }) {
  if (s.peers.length === 0 && s.korea.length === 0) return <Empty>반도체 데이터가 없습니다.</Empty>;
  const cells: Array<[string, number | null]> = [["메모리 현물", s.memory_direction], ["글로벌 peer", s.peer_direction], ["국내 반도체", s.korea_direction], ["EPS 리비전", s.eps_direction]];
  return (
    <div className="ii-semi">
      <div className="ii-semi-verdict">
        {cells.map(([k, v]) => { const w = dirWord(v); return (
          <span key={k} className="ii-semi-cell"><span className="ii-k">{k}</span><b style={{ color: w.c }}>{w.t}</b></span>
        ); })}
      </div>
      <p className="ii-note">{s.interpretation}</p>
      <div className="ii-semi-grid">
        <div>
          <div className="ii-group mono">메모리 가격</div>
          {s.memory.map((p) => (
            <div key={p.id} className="row ii-semi-row" title={p.why}>
              <span className="row-label">{p.label}{p.quality === "MISSING" ? <span className="row-sub" style={{ color: "var(--faint)" }}> 데이터 없음</span> : null}</span>
              <span className={`num ${p.change_1m !== null && p.change_1m >= 0 ? "up" : "down"}`}>{p.quality === "MISSING" ? "–" : `1M ${pct(p.change_1m, 1)}`}</span>
              <MiniBar v={p.z} />
            </div>
          ))}
          {s.missing.length > 0 && <div className="ii-src mono">CSV 적재 경로: data/replay/alternative/&lt;ID&gt;.csv</div>}
        </div>
        <div>
          <div className="ii-group mono">글로벌 peer (직전 세션)</div>
          {s.peers.map((p) => (
            <div key={p.id} className="row ii-semi-row" title={p.why}>
              <span className="row-label">{p.label}{p.quality !== "OK" ? <span className="row-sub" style={{ color: QUALITY[p.quality].color }}> {QUALITY[p.quality].label}</span> : null}</span>
              <span className={`num ${p.change_1d !== null && p.change_1d >= 0 ? "up" : "down"}`}>{pct(p.change_1d)} <span style={{ color: "var(--faint)" }}>{sig(p.z)}</span></span>
              <MiniBar v={p.z} />
            </div>
          ))}
        </div>
        <div>
          <div className="ii-group mono">국내</div>
          {s.korea.map((r) => (
            <div key={r.stock_id} className="row ii-semi-row">
              <span className="row-label">{r.name}</span>
              <span className={`num ${r.change_1d !== null && r.change_1d >= 0 ? "up" : "down"}`}>{pct(r.change_1d)} <span style={{ color: "var(--faint)" }}>{sig(r.z)}</span>{r.volume_z !== null && Math.abs(r.volume_z) >= 1.5 ? <span style={{ color: "var(--warn)" }}> 거래량 {sig(r.volume_z)}</span> : null}</span>
              <MiniBar v={r.z} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
