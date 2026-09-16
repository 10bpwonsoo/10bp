import type { Agreement, Confidence, Quality } from "../api/investment";

export const pct = (v: number | null, d = 2) => (v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}%`);
export const sig = (v: number | null, d = 1) => (v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}σ`);
export const num = (v: number | null, d = 0) => (v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}`);
export const dir = (v: number | null) => (v === null ? "" : v > 0 ? "up" : v < 0 ? "down" : "");
export const price = (v: number | null) =>
  v === null ? "–" : v >= 1000 ? v.toLocaleString("ko-KR", { maximumFractionDigits: 0 }) : v.toFixed(2);

export const AGREEMENT: Record<Agreement, { label: string; color: string }> = {
  confirmed: { label: "확인", color: "var(--ok)" },
  muted: { label: "무반응", color: "var(--muted)" },
  mismatch: { label: "불일치", color: "var(--crit)" },
  unknown: { label: "판정 불가", color: "var(--faint)" },
};
export const CONF_COLOR: Record<Confidence, string> = { HIGH: "var(--ok)", MEDIUM: "var(--warn)", LOW: "var(--faint)" };
export const QUALITY: Record<Quality, { label: string; color: string }> = {
  OK: { label: "", color: "var(--muted)" },
  STALE: { label: "낡음", color: "var(--warn)" },
  PARTIAL: { label: "부분", color: "var(--muted)" },
  MISSING: { label: "없음", color: "var(--faint)" },
};

/** 발산형 작은 막대. 값 v 를 -max~+max 로 그린다. */
export function MiniBar({ v, max = 3 }: { v: number | null; max?: number }) {
  if (v === null) return <span className="ii-bar" aria-hidden="true" />;
  const p = Math.min(1, Math.abs(v) / max) * 50;
  return (
    <span className="ii-bar" aria-hidden="true">
      <span className="ii-bar-fill" style={{ left: v >= 0 ? "50%" : `${50 - p}%`, width: `${p}%`, background: v >= 0 ? "var(--up)" : "var(--down)" }} />
      <span className="ii-bar-zero" />
    </span>
  );
}

export function Tag({ children, color, title }: { children: React.ReactNode; color?: string; title?: string }) {
  return (
    <span className="ii-tag mono" style={{ color: color ?? "var(--muted)", borderColor: color ?? "var(--rule)" }} title={title}>
      {children}
    </span>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="ii-empty">{children}</p>;
}
