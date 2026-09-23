import type { MarketStateHistory, StateHistoryPoint, StateLabel } from "../api/types";

/**
 * Market State · 온도계 한 달 히스토리 (2026-09-23).
 *
 * 같은 시계열을 날짜별로 잘라 같은 엔진(판정 → 온도계)을 다시 돌린 값이다.
 * ① 온도 차트: 종합·가격·뉴스 온도(온도계의 세 바늘)를 날마다 찍고, 그 뒤에 그날
 *    판정의 확신(%)을 옅은 기둥으로 깔아 보조지표로 읽는다. 위의 얇은 띠가 판정 라벨.
 * ② 재료 히트맵: 온도계 재료 스트립(위험선호·변동성·성장·신용·한국 수급·뉴스 감성)의
 *    날짜별 값. 결측은 비워 둔다 — 0 으로 그리지 않는다.
 * 화면은 숫자를 만들지 않는다. 서버가 준 것을 그대로 그린다.
 */
export const LABEL_KO: Record<string, string> = {
  RISK_ON: "Risk-On",
  RISK_OFF: "Risk-Off",
  GROWTH_SHOCK: "Growth Shock",
  INFLATION_SHOCK: "Inflation Shock",
  LIQUIDITY_STRESS: "Liquidity Stress",
  POLICY_DRIVEN: "Policy Driven",
  GEOPOLITICAL_RISK: "Geopolitical Risk",
  NEUTRAL: "판정 없음",
};

/** 라벨 색. 방향(적=위험선호, 청=위험회피)은 기존 up/down 토큰, 나머지는 경고 계열. */
export const LABEL_COLOR: Record<string, string> = {
  RISK_ON: "var(--up)",
  RISK_OFF: "var(--down)",
  GROWTH_SHOCK: "var(--crit)",
  INFLATION_SHOCK: "var(--warn)",
  LIQUIDITY_STRESS: "var(--crit)",
  POLICY_DRIVEN: "var(--info, var(--accent))",
  GEOPOLITICAL_RISK: "var(--warn)",
  NEUTRAL: "var(--faint)",
};

function colorOf(label: StateLabel): string {
  return LABEL_COLOR[label] ?? "var(--faint)";
}
function md(d: string): string {
  return d.slice(5).replace("-", "/");
}
const sgn = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(0)}`;
const fmt = (v: number | null) => (v === null ? "–" : sgn(v));

function cellTitle(p: StateHistoryPoint, labels: Record<string, string>): string {
  const head = `${p.date} · ${LABEL_KO[p.label] ?? p.label}${p.secondary_label ? ` / ${LABEL_KO[p.secondary_label]}` : ""} · 판정 확신 ${p.confidence.toFixed(0)}%`;
  const temps = `종합 ${fmt(p.composite)} · 가격 ${fmt(p.price_temperature)} · 뉴스 ${fmt(p.news_temperature)}${p.news_events ? ` (${p.news_events}건)` : ""} · 온도계 신뢰도 ${p.thermo_confidence.toFixed(0)}%`;
  const comps = Object.entries(p.components).map(([k, v]) => `${labels[k] ?? k} ${fmt(v)}`).join(" · ");
  const drv = p.drivers.length ? `주도: ${p.drivers.join(" · ")}` : "주도 변수 없음";
  return `${head}\n${temps}\n${comps}\n${drv} · 확보 ${(p.coverage * 100).toFixed(0)}%`;
}

/** 값(-100~+100)을 발산형 셀 배경으로. 0 근처는 거의 투명. */
function heat(v: number | null): string {
  if (v === null) return "transparent";
  const a = Math.min(1, Math.abs(v) / 100) * 0.75 + (Math.abs(v) >= 5 ? 0.1 : 0);
  return `color-mix(in oklab, ${v >= 0 ? "var(--up)" : "var(--down)"} ${Math.round(a * 100)}%, transparent)`;
}

export function StateHistoryStrip({ history }: { history: MarketStateHistory | null }) {
  if (!history) return null;
  const pts = history.points;
  if (pts.length === 0) {
    return <div className="sh"><div className="sh-summary" style={{ color: "var(--faint)" }}>히스토리를 재생할 봉이 없습니다.</div></div>;
  }
  const n = pts.length;
  const cols = `repeat(${n}, minmax(0, 1fr))`;
  const labels = history.component_labels;
  const compKeys = Object.keys(labels);
  const xOf = (i: number) => (n === 1 ? 50 : ((i + 0.5) / n) * 100);
  const yOf = (t: number) => 50 - t / 2; // -100..+100 → 100..0 (%)
  const path = (pick: (p: StateHistoryPoint) => number | null) => {
    const segs: string[] = [];
    let cur: string[] = [];
    pts.forEach((p, i) => {
      const t = pick(p);
      if (t === null) { if (cur.length > 1) segs.push(cur.join(" ")); cur = []; return; }
      cur.push(`${xOf(i).toFixed(2)},${yOf(t).toFixed(2)}`);
    });
    if (cur.length > 1) segs.push(cur.join(" "));
    return segs;
  };
  const compSegs = path((p) => p.composite);
  const priceSegs = path((p) => p.price_temperature);
  const newsSegs = path((p) => p.news_temperature);
  const last = pts[n - 1]!;
  const few = pts.map((p, i) => ({ i, p })).filter(({ i, p }) => i === 0 || i === n - 1 || (new Date(p.date).getDay() === 1 && i > 1 && i < n - 2));
  const newsDays = pts.filter((p) => p.news_temperature !== null).length;

  return (
    <div className="sh" data-testid="state-history">
      <div className="sh-head">
        <span className="sh-k">최근 {n}거래일</span>
        <span className="sh-legend">
          {Object.entries(history.days_by_label)
            .sort((a, b) => b[1] - a[1])
            .map(([k, v]) => (
              <span key={k} className="sh-leg">
                <i style={{ background: colorOf(k as StateLabel) }} />
                {LABEL_KO[k] ?? k} <span className="num">{v}</span>
              </span>
            ))}
        </span>
      </div>

      {/* ① 온도 — 종합·가격·뉴스. 뒤의 옅은 기둥 = 그날 판정 확신(%), 위의 띠 = 판정 라벨 */}
      <div className="sh-cap mono">
        ① 온도 <span className="sh-key"><i className="sh-key-comp" /> 종합</span> <span className="sh-key"><i className="sh-key-price" /> 가격</span> <span className="sh-key"><i className="sh-key-news" /> 뉴스{newsDays < n ? ` (${newsDays}일만 기사 있음)` : ""}</span>
        <span className="sh-key"><i className="sh-key-conf" /> 판정 확신 % (보조, 오른쪽 눈금)</span> · 위 띠 = 판정 라벨
      </div>
      <div className="sh-row sh-row-3">
        <div className="sh-y mono" aria-hidden="true">
          <span style={{ top: 0 }}>+100</span>
          <span style={{ top: "50%" }}>0</span>
          <span style={{ bottom: 0 }}>−100</span>
        </div>
        <div className="sh-plot" style={{ gridTemplateColumns: cols }} aria-label="종합·가격·뉴스 온도 추이와 판정 확신">
          <div className="sh-gl sh-gl-0" aria-hidden="true" />
          <div className="sh-gl sh-gl-p" aria-hidden="true" />
          <div className="sh-gl sh-gl-m" aria-hidden="true" />
          {/* 판정 확신 기둥 (보조지표) + 라벨 띠 */}
          {pts.map((p, i) => (
            <div key={`c-${p.date}`} className="sh-conf" style={{ gridColumn: i + 1 }} role="listitem" data-label={p.label} data-date={p.date} data-confidence={p.confidence.toFixed(0)} title={cellTitle(p, labels)}>
              <i className="sh-conf-band" style={{ background: colorOf(p.label) }} />
              <i className="sh-conf-bar" style={{ height: `${Math.max(2, p.confidence)}%` }} />
            </div>
          ))}
          <svg className="sh-line" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {newsSegs.map((d, i) => <polyline key={`n${i}`} points={d} fill="none" stroke="var(--warn)" strokeWidth={1.2} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />)}
            {priceSegs.map((d, i) => <polyline key={`p${i}`} points={d} fill="none" stroke="var(--muted)" strokeWidth={1.2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />)}
            {compSegs.map((d, i) => <polyline key={`s${i}`} points={d} fill="none" stroke="var(--ink)" strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />)}
          </svg>
          {pts.map((p, i) => {
            const t = p.composite;
            return (
              <div key={p.date} className="sh-pt" style={{ gridColumn: i + 1 }} data-date={p.date} data-temp={t === null ? "" : t.toFixed(0)} title={cellTitle(p, labels)}>
                {p.price_temperature !== null && <i className="sh-dot sh-dot-price" style={{ top: `${yOf(p.price_temperature)}%` }} />}
                {p.news_temperature !== null && <i className="sh-dot sh-dot-news" style={{ top: `${yOf(p.news_temperature)}%` }} />}
                {t === null ? (
                  <span className="sh-pt-na mono">–</span>
                ) : (
                  <>
                    <i className="sh-dot sh-dot-comp" style={{ top: `${yOf(t)}%`, background: t >= 0 ? "var(--up)" : "var(--down)" }} />
                    <span className={`sh-pt-val mono ${t >= 0 ? "up" : "down"}`} style={t >= 0 ? { bottom: `${100 - yOf(t) + 5}%` } : { top: `${yOf(t) + 5}%` }}>{sgn(t)}</span>
                  </>
                )}
              </div>
            );
          })}
        </div>
        <div className="sh-y sh-y-r mono" aria-hidden="true">
          <span style={{ top: 0 }}>100%</span>
          <span style={{ top: "50%" }}>50</span>
          <span style={{ bottom: 0 }}>0</span>
        </div>
      </div>

      {/* 날짜 눈금 */}
      <div className="sh-row sh-row-3">
        <div />
        <div>
          <div className="sh-axis-all mono" style={{ gridTemplateColumns: cols }}>
            {pts.map((p) => <span key={p.date}>{md(p.date)}</span>)}
          </div>
          <div className="sh-axis-few mono">
            {few.map(({ i, p }) => <span key={p.date} style={{ left: `${xOf(i).toFixed(2)}%` }}>{md(p.date)}</span>)}
          </div>
        </div>
        <div />
      </div>

      {/* ② 재료 히트맵 — 온도계 스트립의 날짜별 값 */}
      {compKeys.length > 0 && (
        <>
          <div className="sh-cap mono">② 재료 — 온도계 스트립의 날짜별 값 (−100~+100, 적 = +, 청 = −, 빈 칸 = 결측)</div>
          <div className="sh-heat" role="table" aria-label="온도계 재료별 일별 값">
            {compKeys.map((k) => {
              const lastV = last.components[k] ?? null;
              return (
                <div key={k} className="sh-heat-row" role="row">
                  <span className="sh-heat-label">{labels[k]}</span>
                  <div className="sh-heat-cells" style={{ gridTemplateColumns: cols }}>
                    {pts.map((p) => {
                      const v = p.components[k] ?? null;
                      return (
                        <span key={p.date} role="cell" className={`sh-heat-cell mono${v === null ? " sh-heat-na" : ""}`} style={{ background: heat(v) }} title={`${p.date} · ${labels[k]} ${fmt(v)}`} data-value={v === null ? "" : v.toFixed(0)}>
                          {v === null ? "" : Math.round(v)}
                        </span>
                      );
                    })}
                  </div>
                  <span className={`sh-heat-last num ${lastV === null ? "" : lastV >= 0 ? "up" : "down"}`}>{lastV === null ? "결측" : sgn(lastV)}</span>
                </div>
              );
            })}
          </div>
        </>
      )}

      <div className="sh-summary">
        <span className="sh-now">
          지금 <b style={{ color: colorOf(last.label) }}>{LABEL_KO[last.label] ?? last.label}</b> {history.current_streak}일째
          {history.previous_label ? <span style={{ color: "var(--muted)" }}> · 직전 {LABEL_KO[history.previous_label] ?? history.previous_label}</span> : null}
          <span style={{ color: "var(--muted)" }}> · 전환 {history.changes}회</span>
          <span className="num" style={{ color: "var(--muted)" }}> · 종합 {fmt(last.composite)} (가격 {fmt(last.price_temperature)} · 뉴스 {fmt(last.news_temperature)})</span>
          {history.temperature_first_half !== null && history.temperature_second_half !== null ? (
            <span className="num" style={{ color: "var(--muted)" }}> · 온도 전반 {sgn(history.temperature_first_half)} → 후반 {sgn(history.temperature_second_half)}</span>
          ) : null}
        </span>
        <span className="sh-segs">
          {history.segments.slice(-6).map((s) => (
            <span key={`${s.label}-${s.start}`} className="mono sh-seg" title={`${s.start} ~ ${s.end} · 평균 확신 ${s.mean_confidence.toFixed(0)}%`}>
              <i style={{ background: colorOf(s.label) }} />{md(s.start)}{s.days > 1 ? `–${md(s.end)}` : ""} {LABEL_KO[s.label] ?? s.label} {s.days}일
            </span>
          ))}
        </span>
      </div>
      <div className="sh-note">{history.note}</div>
    </div>
  );
}
