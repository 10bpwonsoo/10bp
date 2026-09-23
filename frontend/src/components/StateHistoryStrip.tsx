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
  const n = pts.length;
  const cols = `repeat(${n}, minmax(0, 1fr))`;
  // 선은 퍼센트 좌표의 SVG 한 장(글자 없음), 점과 숫자는 같은 그리드의 칸 안에 HTML 로 —
  // 그래야 늘려도 글자가 찌부되지 않고 x 가 위 막대와 정확히 맞는다.
  const xOf = (i: number) => (n === 1 ? 50 : ((i + 0.5) / n) * 100);
  const yOf = (t: number) => 50 - t / 2; // -100..+100 → 100..0 (%)
  const segs: string[] = [];
  let cur: string[] = [];
  pts.forEach((p, i) => {
    const t = p.price_temperature;
    if (t === null) { if (cur.length > 1) segs.push(cur.join(" ")); cur = []; return; }
    cur.push(`${xOf(i).toFixed(2)},${yOf(t).toFixed(2)}`);
  });
  if (cur.length > 1) segs.push(cur.join(" "));
  const last = pts[n - 1]!;
  const few = pts.map((p, i) => ({ i, p })).filter(({ i, p }) => i === 0 || i === n - 1 || (new Date(p.date).getDay() === 1 && i > 1 && i < n - 2));
  const sgn = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(0)}`;

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

      {/* ① 판정 띠 — 칸 하나가 하루. 색 = 라벨, 높이·숫자 = 그날 판정의 확신(%). */}
      <div className="sh-cap mono">① 판정 — 색 = 라벨 · 막대 높이와 숫자 = 그날 판정의 확신(%)</div>
      <div className="sh-row">
        <div className="sh-y mono" aria-hidden="true">
          <span style={{ top: 0 }}>100</span>
          <span style={{ top: "50%" }}>50</span>
          <span style={{ bottom: 0 }}>0</span>
        </div>
        <div className="sh-cells" style={{ gridTemplateColumns: cols }} role="list" aria-label="일별 Market State (색 = 판정, 높이 = 확신 %)">
          <div className="sh-grid50" aria-hidden="true" />
          {pts.map((p) => (
            <div key={p.date} className="sh-cell" role="listitem" title={cellTitle(p)} data-label={p.label} data-date={p.date}>
              <span className="sh-cell-val mono">{p.confidence.toFixed(0)}</span>
              <div className="sh-bar" style={{ height: `${Math.max(3, p.confidence)}%`, background: colorOf(p.label) }} />
            </div>
          ))}
        </div>
      </div>

      {/* ② 가격 온도 — 온도계의 △가격과 같은 식, −100(결빙)~+100(과열). 점마다 값을 적는다. */}
      <div className="sh-cap mono">② 가격 온도 — 온도계의 △가격과 같은 식 · −100 결빙 ~ +100 과열 · 적 = 0 위, 청 = 0 아래</div>
      <div className="sh-row">
        <div className="sh-y mono" aria-hidden="true">
          <span style={{ top: 0 }}>+100</span>
          <span style={{ top: "50%" }}>0</span>
          <span style={{ bottom: 0 }}>−100</span>
        </div>
        <div className="sh-plot" style={{ gridTemplateColumns: cols }} aria-label="가격 온도 추이">
          <div className="sh-gl sh-gl-0" aria-hidden="true" />
          <div className="sh-gl sh-gl-p" aria-hidden="true" />
          <div className="sh-gl sh-gl-m" aria-hidden="true" />
          <svg className="sh-line" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {segs.map((d, i) => (
              <polyline key={i} points={d} fill="none" stroke="var(--ink-2)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
            ))}
          </svg>
          {pts.map((p) => {
            const t = p.price_temperature;
            const title = `${p.date} · 가격 온도 ${t === null ? "–" : sgn(t)}`;
            return (
              <div key={p.date} className="sh-pt" title={title} data-date={p.date} data-temp={t === null ? "" : t.toFixed(0)}>
                {t === null ? (
                  <span className="sh-pt-na mono">–</span>
                ) : (
                  <>
                    <i className="sh-dot" style={{ top: `${yOf(t)}%`, background: t >= 0 ? "var(--up)" : "var(--down)" }} />
                    <span className={`sh-pt-val mono ${t >= 0 ? "up" : "down"}`} style={t >= 0 ? { bottom: `${100 - yOf(t) + 4}%` } : { top: `${yOf(t) + 4}%` }}>{sgn(t)}</span>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 날짜 눈금 — 넓은 화면은 매일, 좁은 화면은 월요일·양끝만 */}
      <div className="sh-row">
        <div />
        <div>
          <div className="sh-axis-all mono" style={{ gridTemplateColumns: cols }}>
            {pts.map((p) => <span key={p.date}>{md(p.date)}</span>)}
          </div>
          <div className="sh-axis-few mono">
            {few.map(({ i, p }) => <span key={p.date} style={{ left: `${xOf(i).toFixed(2)}%` }}>{md(p.date)}</span>)}
          </div>
        </div>
      </div>

      <div className="sh-summary">
        <span className="sh-now">
          지금 <b style={{ color: colorOf(last.label) }}>{LABEL_KO[last.label] ?? last.label}</b> {history.current_streak}일째
          {history.previous_label ? <span style={{ color: "var(--muted)" }}> · 직전 {LABEL_KO[history.previous_label] ?? history.previous_label}</span> : null}
          <span style={{ color: "var(--muted)" }}> · 전환 {history.changes}회</span>
          {history.temperature_first_half !== null && history.temperature_second_half !== null ? (
            <span className="num" style={{ color: "var(--muted)" }}>
              {" "}· 가격 온도 전반 {sgn(history.temperature_first_half)} → 후반 {sgn(history.temperature_second_half)}
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
      <div className="sh-note">막대 = 그날 판정의 확신(%) · 색 = 판정 라벨 · 선 = 가격 온도(온도계의 △가격, −100 결빙 ~ +100 과열). {history.note}</div>
    </div>
  );
}
