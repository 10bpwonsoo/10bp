import type { ScenarioInfo } from "../api/types";

/**
 * 시연 상황을 우연이 아니라 의도로 통제한다 (설계서 STEP 7.7).
 * 시나리오가 하나뿐이면 표시하지 않는다.
 */
export function ScenarioSwitcher({
  scenarios,
  active,
  onSelect,
}: {
  scenarios: ScenarioInfo[];
  active: string | null;
  onSelect: (name: string) => void;
}) {
  if (scenarios.length < 2) return null;

  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }} role="group" aria-label="시나리오">
      {scenarios.map((s) => {
        const on = s.name === active;
        return (
          <button
            key={s.name}
            type="button"
            onClick={() => onSelect(s.name)}
            title={s.description}
            aria-pressed={on}
            className="mono"
            style={{
              fontSize: 11,
              padding: "3px 9px",
              borderRadius: "var(--radius)",
              border: `1px solid ${on ? "var(--accent)" : "var(--rule)"}`,
              background: on ? "var(--accent-wash)" : "transparent",
              color: on ? "var(--accent)" : "var(--muted)",
            }}
          >
            {s.title || s.name}
          </button>
        );
      })}
    </div>
  );
}
