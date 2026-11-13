/**
 * History 날짜 표시 (2026-10-21) — x축 라벨은 KST Daily Snapshot 날짜 하나만 쓴다.
 * 미국 정규장 날짜(market_date)는 툴팁·메타 줄에서 따로 보인다. 라벨만 솎고, 점(칸)은 숨기지 않는다.
 */
import type { HistoryMergedRow } from "../api/types";

export const md = (iso: string) => iso.slice(5, 10).replace("-", "/");

/** 같은 날짜가 두 번 이상 나오면 그 날짜들 — 렌더링 전에 검증한다(백엔드가 하나로 묶어 보내야 한다). */
export function duplicateDates(dates: string[]): string[] {
  const seen = new Set<string>(); const dup = new Set<string>();
  for (const d of dates) { const k = d.slice(0, 10); if (seen.has(k)) dup.add(k); seen.add(k); }
  return [...dup];
}

/**
 * n 칸 중 라벨을 붙일 칸 — 마지막·첫 칸은 항상, 나머지는 끝에서부터 같은 간격(step). 첫 라벨은 왼쪽 끝에 붙으므로
 * 그 다음 라벨과도 한 step 이상 떨어지게 한다(모자라면 그 라벨 대신 첫 칸).
 * maxLabels ≥ n 이면 전부(데스크톱에서 자리가 있으면 모든 날짜).
 */
export function thinLabels(n: number, maxLabels: number): number[] {
  if (n <= 0) return [];
  if (n === 1) return [0];
  const m = Math.max(2, Math.floor(maxLabels));
  if (m >= n) return Array.from({ length: n }, (_, i) => i);
  const step = Math.ceil((n - 1) / (m - 1));
  const picked: number[] = [];
  for (let i = n - 1; i >= 0; i -= step) picked.push(i);
  picked[picked.length - 1] = 0; // 남은 가장 앞 라벨(< step) 대신 첫 칸 — 첫 칸과 그 다음 라벨 사이가 한 step 이상
  return picked.reverse();
}

/** 칸 폭으로 라벨 수. 칸이 'MM/DD'(10px mono ≈ 32px)보다 넉넉하면 전부, 아니면 라벨 하나에 LABEL_PX 씩(끝 정렬 라벨과의 여유 포함). */
export const LABEL_PX = 44; // 라벨 30px + 끝 정렬 라벨과의 여유
export const ALL_LABELS_MIN_CELL = 33; // 라벨(30px) + 3px — 이보다 넓은 칸이면 모든 날짜
export function maxLabelsFor(widthPx: number, n = Number.POSITIVE_INFINITY): number {
  if (Number.isFinite(n) && n > 0 && widthPx / n >= ALL_LABELS_MIN_CELL) return n;
  return Math.max(2, Math.floor(widthPx / LABEL_PX));
}

/** 'Snapshot 10/21 KST · US 10/20 close' — snapshot 날짜와 미국 장 날짜를 섞지 않고 함께 적는다. */
export function snapshotLine(date: string, marketDate?: string | null): string {
  return `Snapshot ${md(date)} KST${marketDate ? ` · US ${md(marketDate)} close` : ""}`;
}

export function kstTime(iso?: string | null): string {
  if (!iso) return "";
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return "";
  const k = new Date(t.getTime() + 9 * 3600 * 1000);
  const p = (x: number) => String(x).padStart(2, "0");
  return `${p(k.getUTCMonth() + 1)}/${p(k.getUTCDate())} ${p(k.getUTCHours())}:${p(k.getUTCMinutes())} KST`;
}

export function mergedNote(rows?: HistoryMergedRow[]): string {
  if (!rows || !rows.length) return "";
  return `같은 snapshot 날짜의 다른 저장 행 ${rows.length}건 제외: ` + rows.map((r) => `${r.storage_date} ${r.source}${r.market_date ? ` (US ${md(r.market_date)})` : ""}`).join(", ");
}
