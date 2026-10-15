import type { DataMode } from "../api/types";

function hhmmss(d: Date): string {
  return d.toLocaleTimeString("ko-KR", { hour12: false, timeZone: "Asia/Seoul" });
}

/**
 * '지금 업데이트' — 누른 시점에 서버 캐시를 건너뛰고 새로 수집·계산한다.
 *
 * 실데이터 모드는 공급자 50곳을 도느라 수십 초가 걸린다. 그동안 버튼이
 * 그 사실을 말하고 두 번 눌리지 않는다. 정적 배포본에는 서버가 없어
 * 새 수집이 불가능하다 — 버튼을 숨기지 않고 왜 안 되는지를 적는다.
 */
export function RefreshButton({
  onClick,
  busy,
  lastUpdated,
  mode,
  staticNote,
}: {
  onClick: () => void;
  busy: boolean;
  lastUpdated: Date | null;
  mode: DataMode | null;
  staticNote: string | null;
}) {
  if (staticNote) {
    return (
      <span className="refresh">
        <button type="button" className="refresh-btn" disabled title={staticNote}>
          지금 업데이트
        </button>
        <span className="refresh-note">정적 배포본 · 서버 없이는 새 수집 불가</span>
      </span>
    );
  }
  return (
    <span className="refresh">
      <button
        type="button"
        className="refresh-btn"
        onClick={onClick}
        disabled={busy}
        aria-busy={busy}
        title="TTL 캐시를 건너뛰고 지금 새로 수집·계산한다"
      >
        {busy ? "수집 중…" : "지금 업데이트"}
      </button>
      <span className="refresh-note num">
        {busy
          ? mode === "MOCK"
            ? "계산 중"
            : "공급자 50곳을 도는 중 · 수십 초"
          : lastUpdated
            ? `갱신 ${hhmmss(lastUpdated)}`
            : ""}
      </span>
    </span>
  );
}
