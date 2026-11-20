/** STOCK RADAR · MARKET LEADERSHIP 제목 한 줄 (2026-11-03) — 저장된 모든 날짜의 cockpit 으로 규칙을 확인한다 */
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import type { Cockpit } from "../api/types";
import { leaderTitle, radarHeadline } from "../components/radarTitle";

const ROOT = path.resolve(__dirname, "../../../marketpulse/data/archive/2026");
const docs: [string, Cockpit][] = fs.readdirSync(ROOT).filter((m) => /^\d\d$/.test(m)).sort()
  .flatMap((m) => fs.readdirSync(path.join(ROOT, m)).filter((f) => f.endsWith(".json")).sort().map((f) => [f.slice(0, 10), JSON.parse(fs.readFileSync(path.join(ROOT, m, f), "utf8")).cockpit] as [string, Cockpit]))
  .filter(([, c]) => c && c.radar);
const BAD = /RETURN_SPIKE|NEWS_DRIVEN_MOVE|RELATIVE_MOVE|UNEXPLAINED_ACTIVITY|UNUSUAL|SYSTEM|↑↑|\?|확률|매수|매도|전망/;

describe("radarHeadline", () => {
  it("모든 저장 날짜의 radar 종목 — 제목은 한 줄(25자 이내) · 엔진 코드·금지어 없음 · 상태는 네 가지 중 하나", () => {
    expect(docs.length).toBeGreaterThan(5);
    for (const [, c] of docs) for (const r of c.radar) {
      const h = radarHeadline(r, c);
      expect(h.title.length, `${r.name}: ${h.title}`).toBeLessThanOrEqual(25);
      expect(h.title.length).toBeGreaterThan(4);
      expect(h.title + h.sub).not.toMatch(BAD);
      expect(["POSITIVE", "WATCH", "MIXED", "NEGATIVE"]).toContain(h.status);
    }
  });

  it("11/03 — 동인 · 펀더멘털 · 근거 부족을 구분해 적는다", () => {
    const c = docs.find(([d]) => d === "2026-11-03")![1];
    const h = (name: string) => radarHeadline(c.radar.find((r) => r.name === name)!, c);
    expect(h("대한항공")).toMatchObject({ title: "유가 하락 수혜 + 항공주 동반 강세", status: "POSITIVE" });   // Airlines 리더의 동인(유가 ↓)
    expect(h("한화오션").title).toBe("지정학 긴장 속 방산주 동반 강세");
    expect(h("대한항공").sub).toBe("항공주 지수 시장 대비 +4.1σ (1주)");   // Airlines 는 JETS 하나 — breadth 100% 를 '전반 상승' 으로 쓰지 않는다
    expect(h("삼성전자")).toMatchObject({ title: "메모리·HBM 개선 속 상대강도 유지", sub: "SOX 약세에도 시장 대비 견조", status: "POSITIVE" });
    expect(h("현대제철")).toMatchObject({ title: "급등 포착 · 추가 확인 필요", sub: "확인된 펀더멘털 근거 부족", status: "WATCH" });   // 억지로 해석하지 않는다
    expect(h("효성중공업").title).toBe("뉴스성 움직임 · 원인 확인 중");
    expect(h("Vertiv")).toMatchObject({ status: "MIXED" });   // 1주 강세 · 하루 하락, 펀더멘털 미확인
    expect(h("Vertiv").sub).toContain("펀더멘털 확인 전");
  });

  it("펀더멘털이 개선이어도 그날 크게 내렸으면 '상대강도 유지'라고 하지 않는다", () => {
    const c = docs.find(([d]) => d === "2026-11-02")![1];
    const sk = c.radar.find((r) => r.name === "SK하이닉스")!;
    expect(sk.change_1d!).toBeLessThan(0);
    expect(radarHeadline(sk, c)).toMatchObject({ title: "메모리·HBM 개선에도 주가 조정", status: "MIXED" });
  });
});

describe("leaderTitle", () => {
  it("리더마다 왜 강(약)한지 한 줄 — 유가 · 지정학 동인은 문장으로", () => {
    const c = docs.find(([d]) => d === "2026-11-03")![1];
    const t = Object.fromEntries(c.leadership.leaders.map((l) => [l.label, leaderTitle(l)]));
    expect(t["Airlines"]).toBe("유가 하락 수혜로 상대강도 확대");
    expect(t["Defense"]).toBe("지정학 리스크 확대로 방산주 강세");
    // Geopolitical Risk · 섹터 줄은 주식 계열이 하나(ITA · ETF) — breadth 0/100 을 '수혜주 동반' · '종목 전반 확산' 으로 읽지 않는다
    expect(t["Geopolitical Risk"]).toBe("지정학 긴장 속 상대강도 확대");
    expect(t["Consumer Discretionary"]).toBe("경기소비재 시장 대비 강세");
    for (const [, cc] of docs) for (const l of [...cc.leadership.leaders, ...cc.leadership.laggards]) {
      expect(leaderTitle(l)).not.toMatch(BAD);
      if (l.available <= 1) expect(leaderTitle(l)).not.toMatch(/확산|동반/);
    }
  });
});
