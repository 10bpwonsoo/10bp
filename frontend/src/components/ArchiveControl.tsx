import { useEffect, useRef, useState } from "react";
import { ApiError, fetchArchive, fetchArchiveIndex } from "../api/client";
import { missingSections, SECTION_LABEL, type ArchiveIndexRow, type DashboardArchive } from "../api/archive";

/** ISO 시각 → "10/15 08:31 KST" */
export function kstShort(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(d);
  const v = (t: string) => p.find((x) => x.type === t)?.value ?? "";
  return `${v("month")}/${v("day")} ${v("hour")}:${v("minute")} KST`;
}

interface Missing { date: string; before: string[]; after: string[] }

/**
 * 상단 바의 날짜 선택 — [ LIVE ▾ ] 또는 [ ARCHIVE · 2026-10-15 ▾ ].
 * 저장본 목록 · 날짜 입력 · 이전/다음 저장일. 없는 날짜는 지금 값으로 대신하지 않고 가장 가까운 저장일을 보여 준다.
 * 저장본 목록은 열 때 한 번 받는다(폴링 없음).
 */
export function ArchiveControl({ archive, onOpen }: { archive: DashboardArchive | null; onOpen: (a: DashboardArchive | null) => void }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<ArchiveIndexRow[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [missing, setMissing] = useState<Missing | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const c = new AbortController();
    fetchArchiveIndex(c.signal).then(setRows).catch((e) => { if ((e as Error)?.name !== "AbortError") setRows([]); });
    return () => c.abort();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey); };
  }, [open]);

  const load = async (date: string) => {
    setBusy(date); setErr(null); setMissing(null);
    try {
      const a = await fetchArchive(date);
      onOpen(a);
      setOpen(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        const d = (e.detail ?? {}) as { nearest?: { before?: string[]; after?: string[] } };
        const near = d.nearest ?? nearestFrom(rows ?? [], date);
        setMissing({ date, before: near.before ?? [], after: near.after ?? [] });
      } else {
        setErr(e instanceof ApiError ? e.message : "저장본을 불러오지 못했습니다");
      }
    } finally {
      setBusy(null);
    }
  };

  const dates = (rows ?? []).map((r) => r.date);
  const cur = archive?.snapshot_date ?? null;
  const i = cur ? dates.indexOf(cur) : -1;
  const older = i >= 0 ? dates[i + 1] : dates[0];
  const newer = i > 0 ? dates[i - 1] : undefined;

  return (
    <div className="arc" ref={box} data-testid="archive-control">
      <button type="button" className={`arc-btn mono${archive ? " on" : ""}`} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((o) => !o)} data-testid="archive-toggle"
        title={archive ? "저장된 과거 화면을 보는 중 — 눌러서 날짜를 바꾸거나 LIVE 로" : "날짜별 저장 화면 보기"}>
        {archive ? <><span className="arc-tag">ARCHIVE</span><span className="arc-date">{archive.snapshot_date}</span></> : <><span className="arc-live-dot" aria-hidden="true" />LIVE</>}
        <span aria-hidden="true">▾</span>
      </button>
      {open ? (
        <>
          <div className="arc-scrim" onClick={() => setOpen(false)} aria-hidden="true" />
          <div className="arc-pop" role="dialog" aria-label="날짜별 저장 화면" data-testid="archive-pop">
            <div className="arc-pop-h">
              <span className="ai-k mono">Daily Archive</span>
              <span className="arc-pop-note">그날 저장된 데이터 그대로 · 다시 계산하지 않음</span>
            </div>
            <button type="button" className={`arc-row arc-row-live${archive ? "" : " cur"}`} onClick={() => { onOpen(null); setOpen(false); }} data-testid="archive-live">
              <span className="mono"><span className="arc-live-dot" aria-hidden="true" />LIVE</span><span>현재 데이터</span>
            </button>
            <div className="arc-nav">
              <button type="button" className="arc-nav-b mono" disabled={!older || busy !== null} onClick={() => older && load(older)} data-testid="archive-older">◀ 이전 저장일</button>
              <input type="date" id="archive-date" className="arc-input mono" aria-label="날짜 선택" min={dates[dates.length - 1]} max={dates[0]} value={cur ?? ""}
                onChange={(e) => { if (e.target.value) void load(e.target.value); }} data-testid="archive-date-input" />
              <button type="button" className="arc-nav-b mono" disabled={!newer || busy !== null} onClick={() => newer && load(newer)} data-testid="archive-newer">다음 저장일 ▶</button>
            </div>
            {missing ? (
              <div className="arc-missing" role="status" data-testid="archive-missing">
                <b>{missing.date} 저장 화면이 없습니다.</b>
                {missing.before.length || missing.after.length ? (
                  <>
                    <span>가장 가까운 저장일:</span>
                    <span className="arc-missing-btns">
                      {[...missing.before, ...missing.after].map((d) => <button key={d} type="button" className="arc-nav-b mono" onClick={() => load(d)}>{d}</button>)}
                    </span>
                  </>
                ) : <span>저장된 화면이 아직 없습니다.</span>}
              </div>
            ) : null}
            {err ? <div className="arc-missing" role="alert">{err}</div> : null}
            <div className="arc-list" role="list">
              {rows === null ? <div className="arc-empty">저장 목록을 불러오는 중…</div>
                : rows.length === 0 ? <div className="arc-empty">저장된 화면이 아직 없습니다. 매일 07:30 KST 에 저장됩니다.</div>
                : rows.map((r) => (
                  <button key={r.date} type="button" role="listitem" className={`arc-row${r.date === cur ? " cur" : ""}`} onClick={() => load(r.date)} disabled={busy !== null} data-testid="archive-row" data-date={r.date}>
                    <span className="mono arc-row-d">{r.date}</span>
                    <span className="arc-row-m">데이터 {kstShort(r.source_asof)}</span>
                    <span className={`arc-chip mono${r.archive_status === "PARTIAL" ? " partial" : ""}`}>{busy === r.date ? "…" : r.archive_status ?? "?"}</span>
                  </button>
                ))}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

function nearestFrom(rows: ArchiveIndexRow[], date: string): { before: string[]; after: string[] } {
  const ds = rows.map((r) => r.date).sort();
  return { before: ds.filter((d) => d < date).slice(-1), after: ds.filter((d) => d > date).slice(0, 1) };
}

/** 과거 화면임을 알리는 작은 띠. 경고색으로 덮지 않는다. */
export function ArchiveBanner({ archive, onLive }: { archive: DashboardArchive; onLive: () => void }) {
  const miss = missingSections(archive);
  return (
    <div className="arc-banner" role="status" data-testid="archive-banner">
      <span className="arc-banner-k mono">과거 화면 · ARCHIVE · {archive.snapshot_date}{archive.archive_status === "PARTIAL" ? " · PARTIAL" : ""}</span>
      <span className="arc-banner-m">데이터 기준 {kstShort(archive.meta?.source_asof)} · 저장 {kstShort(archive.generated_at)} · 그날 저장된 판정·점수·문구 그대로(다시 계산하지 않음)</span>
      {miss.length ? <span className="arc-banner-miss" data-testid="archive-missing-sections">이 날짜에 없는 섹션: {miss.map((s) => SECTION_LABEL[s] ?? s).join(" · ")} — 지금 값으로 채우지 않음</span> : null}
      <button type="button" className="arc-nav-b mono" onClick={onLive} data-testid="archive-back-live">LIVE로 돌아가기</button>
    </div>
  );
}

/** 저장본에 없는 탭을 열었을 때 — '불러오는 중' 대신 없다고 말한다. */
export function NotArchivedPanel({ what }: { what: string }) {
  return (
    <div className="grid">
      <section className="panel span-3" data-testid="not-archived">
        <div className="panel-body" style={{ color: "var(--muted)" }}>
          <b className="mono" style={{ color: "var(--ink)" }}>DATA UNAVAILABLE FOR THIS DATE</b> · {what} 은(는) 이 날짜 저장본에 없습니다(NOT ARCHIVED). 지금 데이터로 대신 보여 주지 않습니다.
        </div>
      </section>
    </div>
  );
}
