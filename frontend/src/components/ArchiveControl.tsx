import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../api/client";
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

/** ISO 시각의 한국 날짜 YYYY-MM-DD */
export function kstDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

const DAY_KO = ["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"];
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function parseYmd(s: string): Date | null {
  if (!DATE_RE.test(s)) return null;
  const [y, m, d] = s.split("-").map(Number) as [number, number, number];
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d ? dt : null;
}

/** Daily Snapshot 은 월~금만 — 토·일은 고를 수 없다. */
export function isWeekend(s: string): boolean {
  const d = parseYmd(s);
  return d ? d.getUTCDay() === 0 || d.getUTCDay() === 6 : false;
}

/** ◀ ▶ 는 달력의 전날·다음날이 아니라 '이전·다음 저장 snapshot' 으로 움직인다(토·일은 저장이 없으니 저절로 건너뛴다). */
export function prevSaved(dates: string[], cur: string | null): string | undefined {
  const asc = [...dates].sort();
  if (!cur) return asc[asc.length - 1];
  return asc.filter((d) => d < cur).pop();
}

export function nextSaved(dates: string[], cur: string | null): string | undefined {
  if (!cur) return undefined;
  return [...dates].sort().find((d) => d > cur);
}

export type DateCheck =
  | { kind: "ok"; date: string }
  | { kind: "invalid"; text: string }
  | { kind: "weekend" | "missing"; date: string; dayKo: string; prev?: string; next?: string };

/** 날짜 검색 — 형식 · 주말 · 저장 여부. 없는 날짜는 지금 값으로 대신하지 않고 앞뒤 저장일을 알려 준다. */
export function checkDate(text: string, dates: string[]): DateCheck {
  const s = text.trim();
  const d = parseYmd(s);
  if (!d) return { kind: "invalid", text: s };
  const dayKo = DAY_KO[d.getUTCDay()]!;
  const near = { prev: prevSaved(dates, s), next: nextSaved(dates, s) };
  if (dates.includes(s)) return { kind: "ok", date: s };
  if (isWeekend(s)) return { kind: "weekend", date: s, dayKo, ...near };
  return { kind: "missing", date: s, dayKo, ...near };
}

interface Props {
  archive: DashboardArchive | null;
  rows: ArchiveIndexRow[] | null;
  /** LIVE 화면의 날짜(스냅샷 기준 시각의 한국 날짜) */
  liveDate: string | null;
  onSelect: (date: string) => Promise<void>;
  onLive: () => void;
}

/**
 * 상단 바 날짜 탐색 — 데스크톱 [◀] [2026-10-21 ▾] [▶] [LIVE], 좁은 화면 [2026-10-21 ▾] [LIVE].
 * 펼치면 날짜 검색(YYYY-MM-DD) · 달력(저장된 평일만 선택, 토·일 비활성) · 저장 목록.
 */
export function ArchiveControl({ archive, rows, liveDate, onSelect, onLive }: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<DateCheck | { kind: "error"; text: string } | null>(null);
  const [query, setQuery] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const dates = useMemo(() => (rows ?? []).map((r) => r.date), [rows]);
  const status = useMemo(() => Object.fromEntries((rows ?? []).map((r) => [r.date, r.archive_status ?? ""])), [rows]);
  const cur = archive?.snapshot_date ?? null;
  const shown = cur ?? liveDate ?? dates[0] ?? null;
  const [month, setMonth] = useState<string>(() => (shown ?? "2026-10-01").slice(0, 7));

  useEffect(() => { if (shown) setMonth(shown.slice(0, 7)); }, [shown]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey); };
  }, [open]);

  const go = async (date: string) => {
    const c = checkDate(date, dates);
    if (c.kind !== "ok") { setMsg(c); return; }
    setBusy(date); setMsg(null);
    try {
      await onSelect(date);
      setOpen(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setMsg({ kind: "missing", date, dayKo: DAY_KO[parseYmd(date)!.getUTCDay()]!, prev: prevSaved(dates, date), next: nextSaved(dates, date) });
      else setMsg({ kind: "error", text: e instanceof ApiError ? e.message : "저장본을 불러오지 못했습니다" });
    } finally {
      setBusy(null);
    }
  };

  // LIVE 에서 ◀ 는 LIVE 날짜보다 앞선 가장 최근 저장일
  const older = prevSaved(dates, cur ?? liveDate);
  const newer = cur ? nextSaved(dates, cur) : undefined;
  const partial = archive?.archive_status === "PARTIAL";

  return (
    <div className="arc" ref={box} data-testid="archive-control">
      <button type="button" className="arc-step mono" disabled={!older || busy !== null} onClick={() => older && go(older)} data-testid="archive-older" aria-label="이전 저장일" title={older ? `이전 저장일 ${older}` : "이전 저장일 없음"}>◀</button>
      <button type="button" className={`arc-btn mono${archive ? " on" : ""}`} aria-haspopup="dialog" aria-expanded={open} onClick={() => { setOpen((o) => !o); setMsg(null); }} data-testid="archive-toggle"
        title="날짜별 저장 화면 — 검색 · 달력">
        <span className="arc-date" data-testid="archive-date">{shown ?? "날짜"}</span>
        <span aria-hidden="true">▾</span>
      </button>
      <button type="button" className="arc-step mono" disabled={!newer || busy !== null} onClick={() => newer && go(newer)} data-testid="archive-newer" aria-label="다음 저장일" title={newer ? `다음 저장일 ${newer}` : "다음 저장일 없음"}>▶</button>
      {archive ? (
        <button type="button" className={`arc-mode mono on${partial ? " partial" : ""}`} onClick={onLive} data-testid="archive-mode" title="과거 화면 — 누르면 LIVE 로">
          ARCHIVE{partial ? " · PARTIAL" : ""}
        </button>
      ) : (
        <span className="arc-mode mono" data-testid="archive-mode" title="현재 데이터"><span className="arc-live-dot" aria-hidden="true" />LIVE</span>
      )}
      {open ? (
        <>
          <div className="arc-scrim" onClick={() => setOpen(false)} aria-hidden="true" />
          <div className="arc-pop" role="dialog" aria-label="날짜별 저장 화면" data-testid="archive-pop">
            <div className="arc-pop-h">
              <span className="ai-k mono">Daily Snapshot · 월~금 07:30 KST</span>
              <span className="arc-pop-note">그날 저장된 데이터 그대로 · 다시 계산하지 않음</span>
            </div>
            <form className="arc-search" role="search" onSubmit={(e) => { e.preventDefault(); void go(query); }}>
              <input id="archive-search" className="arc-input mono" inputMode="numeric" placeholder="YYYY-MM-DD" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="날짜 검색" data-testid="archive-search" />
              <button type="submit" className="arc-nav-b mono" data-testid="archive-search-go" aria-label="검색">🔍</button>
            </form>
            {msg ? <DateMessage msg={msg} onPick={(d) => void go(d)} /> : null}
            <Calendar month={month} setMonth={setMonth} dates={dates} status={status} selected={cur} live={liveDate} busy={busy} onPick={(d) => void go(d)} />
            <button type="button" className={`arc-row arc-row-live${archive ? "" : " cur"}`} onClick={() => { onLive(); setOpen(false); }} data-testid="archive-live">
              <span className="mono"><span className="arc-live-dot" aria-hidden="true" />LIVE</span><span>{liveDate ? `현재 데이터 · ${liveDate}` : "현재 데이터"}</span>
            </button>
            <div className="arc-list" role="list">
              {rows === null ? <div className="arc-empty">저장 목록을 불러오는 중…</div>
                : rows.length === 0 ? <div className="arc-empty">저장된 화면이 아직 없습니다. 평일 07:30 KST 에 저장됩니다.</div>
                : rows.map((r) => (
                  <button key={r.date} type="button" role="listitem" className={`arc-row${r.date === cur ? " cur" : ""}`} onClick={() => go(r.date)} disabled={busy !== null} data-testid="archive-row" data-date={r.date}>
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

function DateMessage({ msg, onPick }: { msg: DateCheck | { kind: "error"; text: string }; onPick: (d: string) => void }) {
  if (msg.kind === "ok") return null;
  const near = msg.kind === "weekend" || msg.kind === "missing" ? [msg.prev && ["이전", msg.prev], msg.next && ["다음", msg.next]].filter(Boolean) as [string, string][] : [];
  return (
    <div className="arc-missing" role="status" data-testid="archive-missing">
      <b>
        {msg.kind === "invalid" ? `"${msg.text}" — YYYY-MM-DD 형식으로 입력하세요.`
          : msg.kind === "error" ? msg.text
          : msg.kind === "weekend" ? `${msg.date}은 ${msg.dayKo}로 Daily Snapshot 생성 대상이 아닙니다.`
          : `${msg.date} 저장 화면이 없습니다.`}
      </b>
      {near.length ? (
        <span className="arc-missing-btns">
          {near.map(([k, d]) => <button key={d} type="button" className="arc-nav-b mono" onClick={() => onPick(d)} data-testid={`archive-near-${k === "이전" ? "prev" : "next"}`}>{k}: {d}</button>)}
        </span>
      ) : null}
    </div>
  );
}

/** 달력 — 저장된 평일만 고를 수 있다. 토·일은 비활성, 저장이 없는 평일은 비활성 + 빈 표시. */
function Calendar({ month, setMonth, dates, status, selected, live, busy, onPick }: {
  month: string; setMonth: (m: string) => void; dates: string[]; status: Record<string, string>; selected: string | null; live: string | null; busy: string | null; onPick: (d: string) => void;
}) {
  const [y, m] = month.split("-").map(Number) as [number, number];
  const first = new Date(Date.UTC(y, m - 1, 1));
  const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const lead = (first.getUTCDay() + 6) % 7; // 월요일 시작
  const set = new Set(dates);
  const shift = (k: number) => { const d = new Date(Date.UTC(y, m - 1 + k, 1)); setMonth(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`); };
  const cells: (string | null)[] = [...Array(lead).fill(null), ...Array.from({ length: days }, (_, i) => `${month}-${String(i + 1).padStart(2, "0")}`)];
  return (
    <div className="arc-cal" data-testid="archive-calendar">
      <div className="arc-cal-h">
        <button type="button" className="arc-nav-b mono" onClick={() => shift(-1)} aria-label="이전 달">‹</button>
        <span className="mono">{y}.{String(m).padStart(2, "0")}</span>
        <button type="button" className="arc-nav-b mono" onClick={() => shift(1)} aria-label="다음 달">›</button>
      </div>
      <div className="arc-cal-g" role="grid">
        {["월", "화", "수", "목", "금", "토", "일"].map((d, i) => <span key={d} className={`arc-cal-w${i >= 5 ? " we" : ""}`}>{d}</span>)}
        {cells.map((c, i) => {
          if (!c) return <span key={`b${i}`} />;
          const we = isWeekend(c);
          const has = set.has(c);
          const cls = ["arc-cal-d", we ? "we" : "", has ? "has" : "", c === selected ? "sel" : "", c === live ? "live" : "", status[c] === "PARTIAL" ? "partial" : ""].filter(Boolean).join(" ");
          return (
            <button key={c} type="button" className={cls} disabled={we || !has || busy !== null} onClick={() => onPick(c)} data-testid="archive-day" data-date={c}
              title={we ? "토·일 — Daily Snapshot 생성 대상 아님" : has ? `${c} 저장 화면${status[c] === "PARTIAL" ? " · PARTIAL" : ""}` : `${c} 저장 화면 없음`}>
              {Number(c.slice(8))}
            </button>
          );
        })}
      </div>
      <div className="arc-cal-k mono"><span className="arc-cal-dot has" />저장 <span className="arc-cal-dot partial" />PARTIAL <span className="arc-cal-dot none" />없음 · 토·일 제외</div>
    </div>
  );
}

/** 과거 화면임을 알리는 작은 띠. 경고색으로 덮지 않는다. */
export function ArchiveBanner({ archive, onLive }: { archive: DashboardArchive; onLive: () => void }) {
  const miss = missingSections(archive);
  const origin = (archive.meta?.archive_origin as string | undefined) ?? null;
  return (
    <div className="arc-banner" role="status" data-testid="archive-banner">
      <span className="arc-banner-k mono">ARCHIVE{archive.archive_status === "PARTIAL" ? " · PARTIAL" : ""} · {archive.snapshot_date}</span>
      <span className="arc-banner-m">과거 화면 · 데이터 기준 {kstShort(archive.meta?.source_asof)}{archive.cutoff ? ` · cutoff ${kstShort(String(archive.cutoff))}` : ""}{origin === "historical_backfill" ? " · 그 시점 데이터로 재구성" : ""} · 저장된 판정·점수·문구 그대로(다시 계산하지 않음)</span>
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
