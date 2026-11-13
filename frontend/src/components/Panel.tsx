import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  note?: ReactNode;
  span?: 1 | 2 | 3;
  flush?: boolean;
  children: ReactNode;
}

export function Panel({ title, note, span = 1, flush, children }: PanelProps) {
  const spanClass = span === 3 ? "span-3" : span === 2 ? "span-2" : "";
  return (
    <section className={`panel ${spanClass}`}>
      <header className="panel-head">
        <h2 className="panel-title">{title}</h2>
        {note ? <div className="panel-note">{note}</div> : null}
      </header>
      <div className={`panel-body${flush ? " flush" : ""}`}>{children}</div>
    </section>
  );
}

/**
 * 아직 구현하지 않은 단계를 표시한다.
 *
 * 그럴듯한 가짜 숫자로 채우지 않는다. 데모는 좋아 보이겠지만 시스템이
 * 거짓말을 하게 된다 (요구 15-11).
 */
export function Pending({ stage, children }: { stage: string; children: ReactNode }) {
  return (
    <div className="pending">
      <span className="stage">{stage}</span>
      <p style={{ margin: 0 }}>{children}</p>
    </div>
  );
}
