import type { MarketStateHistory, StateHistoryPoint, StateLabel } from "../api/types";

/**
 * Market State 한 달 히스토리 (2026-09-23).
 *
 * 같은 시계열을 날짜별로 잘라 같은 엔진으로 다시 판정한 값이다 — 오늘 판정과
 * 같은 잣대. 뉴스 온도는 재현할 수 없어 가격 온도만 그린다. 서버가 계산한 것을
 * 그대로 그리고, 화면은 숫자를 만들지 않는다.
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

function cellTitle(p: StateHistoryPoint): string {
  const head = `${p.date} · ${LABEL_KO[p.label] ?? p.label}${p.secondary_label ? ` / ${LABEL_KO[p.secondary_label]}` : ""} · 확신 ${p.confidence.toFixed(0)}%`;
  const temp = p.price_temperature === null ? "가격 온도 –" : `가격 온도 ${p.price_temperature >= 0 ? "+" : ""}${p.price_temperature.toFixed(0)}`;
  const cov = `확보 ${(p.coverage * 100).toFixed(0)}%`;
  const drv = p.drivers.length ? `주도: ${p.drivers.join(" · ")}` : "주도 변수 없음";
  return `${head}\n${temp} · ${cov}\n${drv}`;
}

export function StateHistoryStrip({ history }: { history: MarketStateHistory | null }) {
  if (!history) return null;
  const pts = history.points;
  if (pts.length === 0) {
    return <div className="sh"><div className="sh-summary" style={{ color: "var(--faint)" }}>히스토리를 재생할 봉이 없습니다.</div></div>;
  }
  const W = 100; // 퍼센트 좌표. 셀 폭은 CSS grid 가 정한다.
  const H = 36;
  const temps = pts.map((p) => p.price_temperature);
  const xs = pts.map((_, i) => (pts.length === 1 ? 50 : (i / (pts.length - 1)) * W));
  const yOf = (t: number) => H / 2 - (t / 100) * (H / 2 - 3);
  // 값이 있는 구간만 잇는다 — 없는 날을 0 으로 잇지 않는다
  const segs: string[] = [];
  let cur: string[] = [];
  temps.forEach((t, i) => {
    if (t === null) { if (cur.length > 1) segs.push(cur.join(" ")); cur = []; return; }
    cur.push(`${xs[i]!.toFixed(2)},${yOf(t).toFixed(2)}`);
  });
  if (cur.length > 1) segs.push(cur.join(" "));
  const last = pts[pts.length - 1]!;
  const lastTemp = last.price_temperature;
  const ticks = pts.map((p, i) => ({ i, p })).filter(({ i, p }) => i === 0 || i === pts.length - 1 || (new Date(p.date).getDay() === 1 && i > 1 && i < pts.length - 2));

  return (
    <div className="sh" data-testid="state-history">
      <div className="sh-head">
        <span className="sh-k">최근 {pts.length}거래일</span>
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
      {/* 라벨 띠 — 셀 하나가 하루. 높이는 확신. */}
      <div className="sh-cells" style={{ gridTemplateColumns: `repeat(${pts.length}, minmax(0, 1fr))` }} role="list" aria-label="일별 Market State">
        {pts.map((p) => (
          <div key={p.date} className="sh-cell" role="listitem" title={cellTitle(p)} data-label={p.label} data-date={p.date}>
            <div className="sh-bar" style={{ height: `${Math.max(12, p.confidence)}%`, background: colorOf(p.label) }} />
          </div>
        ))}
      </div>
      {/* 가격 온도 — 같은 x 눈금. 0 선 위/아래로 읽는다. */}
      <svg className="sh-temp" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-label="가격 온도 추이">
        <line x1={0} x2={W} y1={H / 2} y2={H / 2} stroke="var(--rule)" strokeWidth={0.4} vectorEffect="non-scaling-stroke" />
        {segs.map((d, i) => (
          <polyline key={i} points={d} fill="none" stroke="var(--ink-2)" strokeWidth={1.4} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        ))}
        {lastTemp !== null && (
          <circle cx={xs[pts.length - 1]} cy={yOf(lastTemp)} r={1.2} fill="var(--ink)" vectorEffect="non-scaling-stroke" />
        )}
      </svg>
      <div className="sh-axis mono">
        {ticks.map(({ i, p }) => (
          <span key={p.date} style={{ left: `${xs[i]!.toFixed(2)}%` }}>{md(p.date)}</span>
        ))}
      </div>
      <div className="sh-summary">
        <span className="sh-now">
          지금 <b style={{ color: colorOf(last.label) }}>{LABEL_KO[last.label] ?? last.label}</b> {history.current_streak}일째
          {history.previous_label ? <span style={{ color: "var(--muted)" }}> · 직전 {LABEL_KO[history.previous_label] ?? history.previous_label}</span> : null}
          <span style={{ color: "var(--muted)" }}> · 전환 {history.changes}회</span>
          {history.temperature_first_half !== null && history.temperature_second_half !== null ? (
            <span className="num" style={{ color: "var(--muted)" }}>
              {" "}· 가격 온도 {history.temperature_first_half >= 0 ? "+" : ""}{history.temperature_first_half.toFixed(0)} → {history.temperature_second_half >= 0 ? "+" : ""}{history.temperature_second_half.toFixed(0)}
            </span>
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
