import type { SentimentThermometer, ThermoComponent } from "../api/types";
import { Pending } from "./Panel";
import { ScoreTooltip } from "./ScoreTooltip";

/**
 * 센티멘트 온도계 (P5).
 *
 * -100(결빙) ~ +100(과열) 한 눈금 위에 바늘 셋을 놓는다.
 *   · 종합 — 굵은 바늘. 0 에서 여기까지 발산형으로 채운다.
 *   · 뉴스 — 눈금 위쪽의 ▽. 뉴스가 말하는 온도.
 *   · 가격 — 눈금 아래쪽의 △. 가격이 말하는 온도.
 * 두 표식의 거리가 곧 "내러티브와 가격이 맞는가" 다. 임계를 넘으면 그
 * 구간에 경고색 띠가 붙는다.
 *
 * 축은 하나다. 두 온도를 다른 눈금에 놓으면 거리를 읽을 수 없다.
 * 표식의 정체는 색이 아니라 모양·위치·라벨이 말한다 — 색은 방향(적=뜨거움,
 * 청=차가움)에만 쓴다.
 */

const W = 420;
const H = 104;
const PAD = 28;
const TRACK_Y = 34;
const TRACK_H = 12;
const TRACK_W = W - PAD * 2;

const BAND_EDGES = [-60, -20, 20, 60];
const BAND_LABELS: Array<[number, string]> = [
  [-80, "결빙"],
  [-40, "냉각"],
  [0, "중립"],
  [40, "온기"],
  [80, "과열"],
];

function xOf(v: number): number {
  const clamped = Math.max(-100, Math.min(100, v));
  return PAD + ((clamped + 100) / 200) * TRACK_W;
}
function fmt(v: number | null, digits = 0): string {
  if (v === null) return "–";
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}`;
}
function heat(v: number): string {
  return v >= 0 ? "var(--up)" : "var(--down)";
}

export function SentimentGauge({ t }: { t: SentimentThermometer | null }) {
  if (!t) {
    return (
      <Pending stage="P5">
        ThermometerEngine 이 붙으면 가격·뉴스·종합 세 온도가 한 눈금에 표시됩니다.
      </Pending>
    );
  }
  if (t.composite === null) {
    return (
      <Pending stage="측정 불가">
        {t.note}
      </Pending>
    );
  }

  const xc = xOf(t.composite);
  const x0 = xOf(0);
  const fillLeft = Math.min(xc, x0);
  const fillW = Math.abs(xc - x0);
  const gapOn = t.gap_flag !== "none" && t.news !== null && t.price !== null;

  return (
    <div className="gauge">
      {/* ── 머리 숫자. 한 화면에 하나뿐인 hero 다 ── */}
      <div className="gauge-hero">
        <ScoreTooltip breakdown={t.composite_breakdown} label="종합 온도 계산 근거">
          <span className="gauge-value" style={{ color: heat(t.composite) }}>
            {fmt(t.composite)}
          </span>
        </ScoreTooltip>
        <span className="gauge-band">{t.band_label}</span>
        <span
          className={`num gauge-trend ${t.trend}`}
          title={
            t.delta === null
              ? "첫 틱이라 직전 값이 없습니다"
              : `직전 틱 대비 ${fmt(t.delta)}`
          }
        >
          {t.trend_arrow}
          {t.delta !== null ? ` ${fmt(t.delta)}` : ""}
        </span>
        <ScoreTooltip breakdown={t.confidence_breakdown} label="온도계 신뢰도">
          <span className="num gauge-conf">신뢰도 {t.confidence.toFixed(0)}%</span>
        </ScoreTooltip>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label={`시장 온도 ${fmt(t.composite)} (${t.band_label}). 가격 ${fmt(t.price)}, 뉴스 ${fmt(t.news)}.`}
        style={{ display: "block", maxWidth: "100%" }}
      >
        {/* 눈금 */}
        <rect
          x={PAD}
          y={TRACK_Y}
          width={TRACK_W}
          height={TRACK_H}
          rx={2}
          fill="var(--surface-2)"
        />
        {BAND_EDGES.map((v) => (
          <line
            key={v}
            x1={xOf(v)}
            x2={xOf(v)}
            y1={TRACK_Y}
            y2={TRACK_Y + TRACK_H}
            stroke="var(--rule-hi, var(--rule))"
            strokeWidth={1}
          />
        ))}
        {/* 발산형 채움. 0 에서 종합까지 */}
        <rect
          x={fillLeft}
          y={TRACK_Y + 1}
          width={fillW}
          height={TRACK_H - 2}
          fill={`color-mix(in oklab, ${heat(t.composite)} 60%, var(--surface-2))`}
        />
        {/* 0 선 — 중립의 기준 */}
        <line
          x1={x0}
          x2={x0}
          y1={TRACK_Y - 3}
          y2={TRACK_Y + TRACK_H + 3}
          stroke="var(--muted)"
          strokeWidth={1}
        />

        {/* 괴리 띠 — 두 표식 사이 */}
        {gapOn && (
          <g>
            <line
              x1={xOf(t.news!)}
              x2={xOf(t.price!)}
              y1={TRACK_Y + TRACK_H + 6}
              y2={TRACK_Y + TRACK_H + 6}
              stroke="var(--warn)"
              strokeWidth={2}
              strokeDasharray="3 3"
            />
            <title>
              {t.gap_flag === "narrative_hot"
                ? `뉴스가 가격보다 ${Math.abs(t.gap!).toFixed(0)} 뜨겁다`
                : `뉴스가 가격보다 ${Math.abs(t.gap!).toFixed(0)} 차갑다`}
            </title>
          </g>
        )}

        {/* ── 1주 전 표식 (GOAL Kickstart 의 'Latest vs 1-week ago' 관례).
            가격의 1주 전은 시계열에서 잰 것이고 뉴스·종합은 저장 스냅샷에서만
            온다. 있는 것만 그린다 — 없는 것을 0 에 그리지 않는다. ── */}
        {t.composite_week_ago !== null && (
          <line
            x1={xOf(t.composite_week_ago)}
            x2={xOf(t.composite_week_ago)}
            y1={TRACK_Y - 5}
            y2={TRACK_Y + TRACK_H + 5}
            stroke="var(--muted)"
            strokeWidth={1.2}
            strokeDasharray="2 2"
          >
            <title>1주 전 종합 {fmt(t.composite_week_ago)}</title>
          </line>
        )}
        {t.news_week_ago !== null && (
          <polygon
            points={`${xOf(t.news_week_ago) - 4},${TRACK_Y - 11} ${xOf(t.news_week_ago) + 4},${TRACK_Y - 11} ${xOf(t.news_week_ago)},${TRACK_Y - 4}`}
            fill="none"
            stroke="var(--muted)"
            strokeWidth={1.2}
          >
            <title>1주 전 뉴스 {fmt(t.news_week_ago)}</title>
          </polygon>
        )}
        {t.price_week_ago !== null && (
          <polygon
            points={`${xOf(t.price_week_ago) - 4},${TRACK_Y + TRACK_H + 11} ${xOf(t.price_week_ago) + 4},${TRACK_Y + TRACK_H + 11} ${xOf(t.price_week_ago)},${TRACK_Y + TRACK_H + 4}`}
            fill="none"
            stroke="var(--muted)"
            strokeWidth={1.2}
          >
            <title>1주 전 가격 {fmt(t.price_week_ago)}</title>
          </polygon>
        )}

        {/* 종합 바늘. 배경색 링을 먼저 그려 채움과 분리한다 */}
        <line x1={xc} x2={xc} y1={TRACK_Y - 8} y2={TRACK_Y + TRACK_H + 8} stroke="var(--surface)" strokeWidth={6} />
        <line x1={xc} x2={xc} y1={TRACK_Y - 8} y2={TRACK_Y + TRACK_H + 8} stroke="var(--ink)" strokeWidth={2}>
          <title>종합 {fmt(t.composite)} · {t.band_label}</title>
        </line>

        {/* 뉴스 ▽ — 눈금 위 */}
        {t.news !== null ? (
          <g>
            <polygon
              points={`${xOf(t.news) - 5},${TRACK_Y - 12} ${xOf(t.news) + 5},${TRACK_Y - 12} ${xOf(t.news)},${TRACK_Y - 4}`}
              fill="var(--ink-2)"
              stroke="var(--surface)"
              strokeWidth={1.5}
            />
            <text
              className="mono"
              x={xOf(t.news)}
              y={TRACK_Y - 16}
              fontSize={9.5}
              textAnchor="middle"
              fill="var(--ink-2)"
            >
              뉴스 {fmt(t.news)}
            </text>
            <title>뉴스가 말하는 온도 {fmt(t.news)} · 기사 {t.news_events}건</title>
          </g>
        ) : (
          <text className="mono" x={PAD} y={TRACK_Y - 16} fontSize={9.5} fill="var(--faint)">
            뉴스 – (기사 없음)
          </text>
        )}

        {/* 가격 △ — 눈금 아래 */}
        {t.price !== null ? (
          <g>
            <polygon
              points={`${xOf(t.price) - 5},${TRACK_Y + TRACK_H + 12} ${xOf(t.price) + 5},${TRACK_Y + TRACK_H + 12} ${xOf(t.price)},${TRACK_Y + TRACK_H + 4}`}
              fill="var(--ink-2)"
              stroke="var(--surface)"
              strokeWidth={1.5}
            />
            <text
              className="mono"
              x={xOf(t.price)}
              y={TRACK_Y + TRACK_H + 23}
              fontSize={9.5}
              textAnchor="middle"
              fill="var(--ink-2)"
            >
              가격 {fmt(t.price)}
            </text>
            <title>가격이 말하는 온도 {fmt(t.price)}</title>
          </g>
        ) : (
          <text className="mono" x={PAD} y={TRACK_Y + TRACK_H + 23} fontSize={9.5} fill="var(--faint)">
            가격 – (factor 없음)
          </text>
        )}

        {/* 구간 이름 */}
        {BAND_LABELS.map(([v, label]) => (
          <text
            key={label}
            className="mono"
            x={xOf(v)}
            y={H - 6}
            fontSize={9}
            textAnchor="middle"
            fill="var(--faint)"
            letterSpacing=".06em"
          >
            {label}
          </text>
        ))}
        <text className="mono" x={PAD} y={H - 18} fontSize={8.5} textAnchor="start" fill="var(--faint)">−100</text>
        <text className="mono" x={W - PAD} y={H - 18} fontSize={8.5} textAnchor="end" fill="var(--faint)">+100</text>
      </svg>

      {/* ── 숫자 줄. 각 값은 계산 근거로 열린다 ── */}
      <div className="gauge-legs">
        <ScoreTooltip breakdown={t.price_breakdown} label="가격 온도 계산 근거">
          <span className="num">
            <span className="gauge-leg-k">△ 가격</span> {fmt(t.price)}
          </span>
        </ScoreTooltip>
        <ScoreTooltip breakdown={t.news_breakdown} label="뉴스 온도 계산 근거">
          <span className="num">
            <span className="gauge-leg-k">▽ 뉴스</span> {fmt(t.news)}
            {t.news !== null && (
              <span style={{ color: "var(--faint)" }}>
                {" "}· {t.news_events}건{t.llm_events > 0 ? ` (AI ${t.llm_events})` : ""}
              </span>
            )}
          </span>
        </ScoreTooltip>
        {gapOn && (
          <span className="num" style={{ color: "var(--warn)" }}>
            격차 {fmt(t.gap)}
          </span>
        )}
        <span
          className="num"
          style={{ color: "var(--faint)", fontSize: 11 }}
          title={
            t.week_ago_source === "snapshot"
              ? `1주 전 저장 스냅샷 (${t.week_ago_as_of ? new Date(t.week_ago_as_of).toLocaleDateString("ko-KR") : ""}) 과 시계열에서`
              : t.week_ago_source === "series"
                ? "가격의 1주 전은 시계열(5봉 전)에서 잰다. 뉴스·종합의 1주 전은 저장된 스냅샷이 없어 표시하지 않는다."
                : "1주 전 값을 잴 수 없다"
          }
        >
          {t.week_ago_source === "none"
            ? "1주 전 –"
            : `1주 전 △${fmt(t.price_week_ago)}${t.news_week_ago !== null ? ` ▽${fmt(t.news_week_ago)}` : ""}${t.composite_week_ago !== null ? ` 종합 ${fmt(t.composite_week_ago)}` : ""}`}
        </span>
      </div>

      <SentimentStrip components={t.components} composite={t.composite} compositeWeekAgo={t.composite_week_ago} />

      <p className="gauge-note">{t.note}</p>
    </div>
  );
}

/**
 * 재료 스트립 (GOAL Kickstart Exhibit 34 차용).
 *
 * 온도를 만든 재료를 한 줄씩, 같은 눈금(-100~+100) 위에 ● 현재와 ◇ 1주 전으로
 * 찍는다. "어느 재료가 온도를 올렸는가" 가 한눈에 보여야 온도계가 설명
 * 가능해진다 (요구 15-6). 결측 재료도 줄은 남긴다 — 값 없이. 온도가 무엇
 * 없이 만들어졌는지도 정보다.
 */
function SentimentStrip({
  components,
  composite,
  compositeWeekAgo,
}: {
  components: ThermoComponent[];
  composite: number | null;
  compositeWeekAgo: number | null;
}) {
  if (components.length === 0) return null;
  const pos = (v: number) => `${((Math.max(-100, Math.min(100, v)) + 100) / 200) * 100}%`;
  const rows: Array<{ key: string; label: string; value: number | null; week: number | null; title: string; head?: boolean; missing?: boolean }> = [
    {
      key: "composite",
      label: "종합",
      value: composite,
      week: compositeWeekAgo,
      title: "가격·뉴스 가중 결합",
      head: true,
    },
    ...components.map((c) => ({
      key: c.key,
      label: c.label,
      value: c.value,
      week: c.week_ago,
      title: `${c.note}${c.quality ? ` · 품질 ${c.quality}` : ""}`,
      missing: c.value === null,
    })),
  ];
  return (
    <div className="strip" role="table" aria-label="온도계 재료별 현재값과 1주 전 값">
      <div className="strip-axis-head mono" aria-hidden="true">
        <span />
        <span className="strip-axis-head-mid">
          <span>냉각</span>
          <span>◇ 1주 전 · ● 현재</span>
          <span>과열</span>
        </span>
        <span />
      </div>
      {rows.map((r) => (
        <div
          key={r.key}
          className={`strip-row${r.head ? " strip-head" : ""}${r.missing ? " strip-missing" : ""}`}
          role="row"
          title={r.title}
        >
          <span className="strip-label">{r.label}</span>
          <span className="strip-axis" aria-hidden="true">
            <span className="strip-zero" />
            {r.week !== null && <span className="strip-ghost" style={{ left: pos(r.week) }} />}
            {r.value !== null && (
              <span
                className="strip-dot"
                style={{ left: pos(r.value), background: r.value >= 0 ? "var(--up)" : "var(--down)" }}
              />
            )}
          </span>
          <span className={`num strip-val ${r.value === null ? "" : r.value >= 0 ? "up" : "down"}`}>
            {r.value === null ? "결측" : fmt(r.value)}
          </span>
        </div>
      ))}
    </div>
  );
}
