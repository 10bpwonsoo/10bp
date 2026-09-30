import { useState } from "react";
import type { CkIssuePath, CkPathCheck, CkPathStage, CkPathStatus, CkPathStock } from "../api/types";
import { GLOSSARY, MATCH_COLOR, STATUS_KO, STATUS_KO_SHORT, TIER_TIP, glossaryFor } from "./ko";

/**
 * WHAT MATTERS NEXT · MARKET TRANSMISSION PATH — 이슈를 누르면 열리는 accordion.
 * 읽는 순서: SUMMARY(주요 영향 · 단계 확인 수 · 가장 노출된 곳 · 상대적 예외) → EXPECTED vs OBSERVED(+한 줄 해석)
 * → TRANSMISSION PATH(① TRIGGER ▼ ② TRANSMISSION ▼ ③ ASSET IMPACT ▼ ④ THEME / INDUSTRY, 단계마다 영어 상태 + 한글 의미)
 * → STOCK IMPACT(DIRECT 4 · SECONDARY 3 · TERTIARY 접기, 종목마다 EXPECTED / OBSERVED / 상태 + 의미) → WHAT WOULD CONFIRM?(n / m conditions confirmed + 해석).
 * 영어 taxonomy 는 그대로, 한글은 보조. 색은 좋고 나쁨이 아니라 시나리오와 실제 시장의 일치 정도. CONTRADICTED 는 오류가 아니라 '다른 driver 가 더 강하다'.
 */
export const PATH_COLOR: Record<CkPathStatus, string> = { CONFIRMED: MATCH_COLOR.CONFIRMED!, PARTIAL: MATCH_COLOR.PARTIAL!, UNCONFIRMED: MATCH_COLOR.UNCONFIRMED!, CONTRADICTED: MATCH_COLOR.CONTRADICTED!, "DATA MISSING": MATCH_COLOR["DATA MISSING"]! };
const sg = (v: number | null | undefined, d = 1, unit = "") => (v === null || v === undefined ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}${unit}`);

function Ps({ s, ko, compact }: { s: CkPathStatus; ko?: string; compact?: boolean }) {
  return (
    <span className="ck-sk ck-p-st-c" data-status={s}>
      <span className="mono ck-p-st" style={{ color: PATH_COLOR[s] }}>{s}</span>
      {compact ? <span className="ck-sk-short" style={{ display: "inline" }}>· {STATUS_KO_SHORT[s]}</span> : <><span className="ck-sk-ko">{ko ?? STATUS_KO[s]}</span><span className="ck-sk-short">· {STATUS_KO_SHORT[s]}</span></>}
    </span>
  );
}

const CHECK_KO: Record<CkPathStatus, string> = { CONFIRMED: "현재 시장에서 확인", PARTIAL: "일부만 나타남", UNCONFIRMED: "아직 나타나지 않음", CONTRADICTED: "반대 방향", "DATA MISSING": "데이터 없음" };
const STAGE_TITLE: Record<string, string> = { trigger: "TRIGGER", first_order: "TRANSMISSION", assets: "ASSET IMPACT", themes: "THEME / INDUSTRY" };
const STAGE_KO: Record<CkPathStatus, string> = { CONFIRMED: "현재 시장에서도 해당 전파가 확인됨", PARTIAL: "일부 자산에서만 확인됨", UNCONFIRMED: "아직 시장에서 확인되지 않음", CONTRADICTED: "예상과 반대 — 다른 driver 가 더 강함", "DATA MISSING": "확인할 데이터 없음" };

function Term({ text }: { text: string }) {
  const tip = glossaryFor(text);
  return <span title={tip} className={tip ? "ck-term" : undefined}>{text}</span>;
}

function Stage({ st, n, arrowBelow }: { st: CkPathStage; n: number; arrowBelow: boolean }) {
  return (
    <div className="ck-p-stage" data-testid="ck-path-stage" data-key={st.key}>
      <div className="ck-p-stage-h"><span><span className="ck-p-stage-num mono">{["①", "②", "③", "④"][n - 1]}</span><span className="ck-k mono">{STAGE_TITLE[st.key] ?? st.label}</span>{STAGE_TITLE[st.key] && st.label !== STAGE_TITLE[st.key] ? <span className="mono ck-p-stage-l"> · <Term text={st.label} /></span> : null}</span><Ps s={st.status} ko={STAGE_KO[st.status]} /></div>
      {st.explain ? <div className="ck-p-stage-ex">{st.explain}</div> : null}
      {st.text.length ? <div className="ck-p-stage-t">{st.text.map((t, i) => <span key={i}><Term text={t} />{i < st.text.length - 1 ? " · " : ""}</span>)}</div> : null}
      {st.checks.length ? (
        <div className="ck-p-checks">
          {st.checks.map((c: CkPathCheck, i) => (
            <div key={`${c.id}-${i}`} className="ck-p-check mono"><span className="ck-p-check-l"><Term text={c.label} /></span><span className="ck-p-check-e">{c.expect > 0 ? "↑" : "↓"} 기대</span><span className="num">{c.observed_text}</span><Ps s={c.status} ko={CHECK_KO[c.status]} compact /></div>
          ))}
        </div>
      ) : null}
      {arrowBelow ? <div className="ck-p-arrow mono" aria-hidden="true">▼</div> : null}
    </div>
  );
}

function StockRow({ s, onStock }: { s: CkPathStock; onStock?: (id: string) => void }) {
  const contra = s.status === "CONTRADICTED";
  return (
    <div className={`ck-p-stock2${s.in_radar ? " radar" : ""}`} data-testid="ck-path-stock" onClick={s.in_radar && onStock ? (e) => { e.stopPropagation(); onStock(s.id); } : undefined} role={s.in_radar && onStock ? "button" : undefined}>
      <span className="ck-p-stock-n"><b>{s.name}</b>{s.in_radar ? <em className="ck-p-radar" title="STOCK RADAR 에 있는 종목 — 누르면 radar 로">RADAR ●</em> : null}</span>
      <span className="ck-p-ex-t"><i>Expected</i><span>{s.expected_text || s.arrow}</span></span>
      <span className="ck-p-ob-t num"><i>Observed</i><span>{s.z === null ? "–" : `${sg(s.z)}σ ${s.z > 0 ? "↑" : s.z < 0 ? "↓" : "→"}`}</span></span>
      <Ps s={s.status} ko={s.status === "CONFIRMED" ? "예상 방향과 실제 가격이 일치" : s.status === "CONTRADICTED" ? "예상과 반대로 움직임" : s.status === "PARTIAL" ? "예상 방향이지만 움직임이 작음" : s.status === "UNCONFIRMED" ? "아직 뚜렷한 움직임 없음" : "가격 데이터 없음"} />
      {contra ? <span className="ck-p-note">금리·매크로 부담보다 종목·테마 고유 driver 가 더 강하게 작용하고 있을 가능성 — 오류가 아니라 확인할 신호</span> : null}
    </div>
  );
}

export function IssuePathView({ p, status, current, title, onStock }: { p: CkIssuePath; status: string; current: string; title?: string; onStock?: (id: string) => void }) {
  const [all, setAll] = useState(false);
  const show = (tier: string) => (all ? Infinity : (p.tier_show[tier] ?? p.tier_max));
  const hidden = p.tiers.reduce((n, t) => n + Math.max(0, t.stocks.length - Math.min(t.stocks.length, show(t.tier))), 0);
  const sm = p.summary;
  return (
    <div className="ck-path" data-testid="ck-path" onClick={(e) => e.stopPropagation()}>
      {sm ? (
        <div className="ck-p-sum" data-testid="ck-path-summary">
          <div className="full"><span className="ck-k mono">Summary{title ? ` · ${title.replace(/는가\??$/, "면")}` : ""}</span></div>
          <div className="full"><span className="ck-k mono">Main impact</span><span className="ck-p-sum-chain">{sm.main_impact.map((x, i) => <span key={i}><Term text={x} />{i < sm.main_impact.length - 1 ? " → " : ""}</span>)}</span></div>
          <div><span className="ck-k mono">Current transmission</span><span className="ck-p-sum-n num">{sm.stages_confirmed} / {sm.stages_total} stages confirmed</span><span className="ck-sub-i">{sm.stages_text}</span></div>
          <div><span className="ck-k mono">Status · Current</span><span className="mono">{status} <span className="ck-sub-i">· {STATUS_KO[status] ?? ""}</span></span><span className="mono ck-sub-i">{current}</span></div>
          <div><span className="ck-k mono">Most exposed</span><span>{sm.most_exposed.length ? sm.most_exposed.join(" / ") : "–"}</span></div>
          <div><span className="ck-k mono">Relative exception</span><span>{sm.exception.length ? sm.exception.join(" / ") : "–"}<span className="ck-sub-i"> {sm.exception.length ? "예상과 달리 버티는 곳" : "예상과 반대로 버티는 테마 없음"}</span></span></div>
        </div>
      ) : null}
      <div className="ck-p-ex2" data-testid="ck-path-expected-observed">
        <div><span className="ck-k mono">Expected</span><span className="ck-sub-i">일반적으로 예상되는 시장 반응</span><span>{p.expected}</span></div>
        <div><span className="ck-k mono">Observed</span><span className="ck-sub-i">현재 실제 시장에서 나타나는 반응</span>
          {p.themes.checks.length ? p.themes.checks.map((c) => (
            <div key={c.id + c.label} className="ck-p-obs-row"><span>{c.label}</span><span className="mono" style={{ color: PATH_COLOR[c.status] }}>{c.status === "CONFIRMED" || c.status === "PARTIAL" ? (c.expect < 0 ? "WEAK" : "STRONG") : c.status === "CONTRADICTED" ? "RESILIENT" : c.status} <small>{c.status === "CONFIRMED" ? "예상 방향과 같은 방향" : c.status === "PARTIAL" ? "일부 확인" : c.status === "CONTRADICTED" ? "예상보다 견조" : c.status === "DATA MISSING" ? "데이터 없음" : "움직임 작음"}</small></span></div>
          )) : <span>{p.observed}</span>}
        </div>
        {sm?.observed_read ? <div className="full ck-p-concl" data-testid="ck-path-observed-read">{sm.observed_read}</div> : null}
      </div>
      <div>
        <div className="ck-p-stage-h"><span className="ck-k mono">Transmission path</span><span className="ck-sub-i">영어 단계명은 시스템 용어, 아래 한글은 왜 그 단계로 이어지는지</span></div>
        <div className="ck-p-flow">
          <Stage st={p.trigger} n={1} arrowBelow />
          <Stage st={p.first_order} n={2} arrowBelow />
          <Stage st={p.assets} n={3} arrowBelow />
          <Stage st={p.themes} n={4} arrowBelow={p.tiers.length > 0} />
        </div>
      </div>
      {p.tiers.length ? (
        <div className="ck-p-tiers" data-testid="ck-path-tiers">
          <div className="ck-p-stage-h"><span className="ck-k mono">Stock impact</span><span className="ck-sub-i">실제 종목에서 해당 영향이 나타나는지 — 관련성만으로 판정하지 않고 종목 가격으로 확인</span></div>
          {p.tiers.map((t) => {
            const lim = show(t.tier); const rows = t.stocks.slice(0, lim);
            return (
              <div key={t.tier} className="ck-p-tier">
                <div className="ck-p-tier-h"><span className="ck-k mono" title={TIER_TIP[t.tier]}>{t.tier}</span><span className="ck-p-tier-ko">{STATUS_KO[t.tier]} · {TIER_TIP[t.tier]}</span>{rows.length < t.stocks.length ? <span className="ck-sub-i">{rows.length ? `${rows.length} / ${t.stocks.length}` : `${t.stocks.length}종목 접힘`}</span> : null}</div>
                {rows.map((s) => <StockRow key={s.id} s={s} onStock={onStock} />)}
              </div>
            );
          })}
          {hidden > 0 && !all ? <button type="button" className="ck-more" onClick={() => setAll(true)}>View all stocks (+{hidden})</button> : null}
        </div>
      ) : null}
      <div className="ck-p-concl" data-testid="ck-path-conclusion">{p.conclusion}</div>
      {p.confirm.length ? (
        <div className="ck-p-confirm" data-testid="ck-path-confirm">
          <div className="ck-p-stage-h"><span><span className="ck-k mono">What would confirm?</span> <span className="ck-sub-i">이 시나리오가 더 강해지려면 무엇이 추가로 나타나야 하는가</span></span><span className="mono num">{p.confirm_count} / {p.confirm.length} conditions confirmed</span></div>
          <div className="ck-sub-i">{p.confirm.length}개 확인 조건 중 {p.confirm_count}개 충족 — 확률이 아니라 조건 수</div>
          {p.confirm.map((c, i) => <div key={i} className="ck-p-cf2 mono"><span>{c.status === "CONFIRMED" ? "☑" : c.status === "PARTIAL" ? "△" : "☐"}</span><span><Term text={c.label} /></span><span className="num">{c.observed_text}</span><Ps s={c.status} ko={CHECK_KO[c.status]} /></div>)}
          {sm?.confirm_read ? <div className="ck-p-concl" data-testid="ck-path-confirm-read">{sm.confirm_read}</div> : null}
        </div>
      ) : null}
      <div className="ck-legend mono" title={Object.entries(GLOSSARY).map(([k, v]) => `${k}: ${v}`).join("\n")}>색상은 수익률의 좋고 나쁨이 아니라 현재 시나리오와 실제 시장의 일치 여부를 뜻합니다. 밑줄 친 용어에 마우스를 올리면 뜻이 보입니다.</div>
    </div>
  );
}
