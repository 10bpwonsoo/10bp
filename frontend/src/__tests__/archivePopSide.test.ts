/** 날짜 펼침 창 — 버튼이 화면 왼쪽에 있으면 왼쪽 끝에 붙여 화면 밖으로 잘리지 않는다(2026-11-04 iPad). */
import { describe, expect, it } from "vitest";
import { popSide } from "../components/ArchiveControl";

const el = (left: number, right: number) => ({ getBoundingClientRect: () => ({ left, right }) }) as unknown as HTMLElement;

describe("popSide", () => {
  it("버튼 오른쪽 끝 기준 320px 이 화면 왼쪽 밖으로 나가면 left", () => {
    expect(popSide(el(46, 145))).toBe("left");   // 1180px 에서 머리줄이 접혀 날짜 버튼이 왼쪽에 온 경우
  });
  it("오른쪽에 있는 버튼은 그대로 right", () => {
    expect(popSide(el(1163, 1262))).toBe("right");
    expect(popSide(el(386, 484))).toBe("right");
  });
  it("요소가 없으면 기본 right", () => {
    expect(popSide(null)).toBe("right");
  });
});
