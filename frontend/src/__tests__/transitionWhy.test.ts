/**
 * RECENT TRANSITIONS 의 "왜 바뀌었나" — 저장된 모든 날짜 화면의 모든 전환에 대해:
 * 문장이 regime 결론으로 끝나고, raw ticker · 엔진 코드 · 금지어가 없고, 근거는 2~3개, 미래 정보(그 행 스냅샷 cutoff 이후)를 쓰지 않는다.
 */
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, existsSync, writeFileSync } from "fs";
import { join } from "path";
import type { CkRegimeHistory } from "../api/types";
import { dayDocDateFor, dayDocMatches, explainTransition, type TransitionDayDoc } from "../components/transitionWhy";

const ROOT = join(__dirname, "../../../marketpulse/data/archive");
const files = existsSync(ROOT) ? readdirSync(join(ROOT, "2026")).flatMap((m) => readdirSync(join(ROOT, "2026", m)).map((f) => join(ROOT, "2026", m, f))) : [];
const docs = new Map<string, any>(files.map((f) => { const d = JSON.parse(readFileSync(f, "utf-8")); return [d.snapshot_date as string, d]; }));
const dates = [...docs.keys()].sort();

function rows() {
  const out: { view: string; date: string; from: string; to: string; r: ReturnType<typeof explainTransition>; doc: TransitionDayDoc | null }[] = [];
  for (const v of dates) {
    const h = docs.get(v).cockpit?.history as CkRegimeHistory | undefined;
    if (!h) continue;
    for (const t of h.transitions) {
      const i = h.days.findIndex((d) => d.date === t.date);
      const prev = i > 0 ? h.days[i - 1]!.date : null;
      const dd = dayDocDateFor(t.date, dates.filter((x) => x <= v));
      const doc = dd && dayDocMatches(docs.get(dd), t.date) ? (docs.get(dd) as TransitionDayDoc) : null;
      out.push({ view: v, date: t.date, from: t.from_label, to: t.to_label, r: explainTransition(t, prev, doc, h.days), doc });
    }
  }
  return out;
}

describe("transition why", () => {
  const all = rows();
  it("저장본이 있다", () => { expect(all.length).toBeGreaterThan(5); });
  it("문장 규칙 — 결론으로 끝, raw ticker · 엔진 코드 · 금지어 없음, 근거 칩 1~3개", () => {
    for (const x of all) {
      expect(x.r.why.endsWith("다.")).toBe(true);
      expect(x.r.why).not.toMatch(/US_HY_OAS|NDX|SPX|σ|_[A-Z]|확률|매수|매도|전망/);
      expect(x.r.chips.length).toBeGreaterThanOrEqual(1);
      expect(x.r.chips.length).toBeLessThanOrEqual(3);
    }
  });
  it("미래 정보 없음 — 쓴 스냅샷은 그 행(D)을 마지막 행으로 가진 D 이후 첫 저장본, 화면 날짜보다 늦지 않다", () => {
    for (const x of all) {
      if (!x.doc) continue;
      expect(x.doc.snapshot_date > x.date).toBe(true);
      expect(x.doc.snapshot_date <= x.view).toBe(true);
      expect(x.doc.cockpit!.history!.days!.at(-1)!.date).toBe(x.date);
      for (const u of x.r.used) if (u.kind === "event") expect(u.raw.slice(0, 5) <= x.date.slice(5).replace("-", "/")).toBe(true);
    }
  });
  it("같은 전환은 어느 날짜 화면에서 봐도 같은 이유(저장본만 읽으니까)", () => {
    const by = new Map<string, Set<string>>();
    for (const x of all) { if (!x.doc) continue; const k = x.date; if (!by.has(k)) by.set(k, new Set()); by.get(k)!.add(x.r.why); }
    for (const [, s] of by) expect(s.size).toBe(1);
  });
  it("보고서", () => {
    const uniq = new Map<string, (typeof all)[number]>();
    for (const x of all) uniq.set(x.date, x);
    const rep = [...uniq.values()].sort((a, b) => b.date.localeCompare(a.date)).map((x) => ({ date: x.date, transition: `${x.from} → ${x.to}`, why: x.r.why, chips: x.r.chips, meaning: x.r.meaning, basis: x.r.basis, evidence: x.r.evidence, dayDoc: x.r.dayDoc }));
    if (process.env.TW_REPORT) writeFileSync(process.env.TW_REPORT, JSON.stringify(rep, null, 1));
    expect(rep.length).toBeGreaterThan(0);
  });
});
