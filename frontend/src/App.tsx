import { useEffect, useState } from "react";
import { fetchInfo, fetchScenarios } from "./api/client";
import type { ApiInfo, DataMode, ScenarioInfo } from "./api/types";
import { useSnapshot } from "./api/useSnapshot";
import { DataModeBadge } from "./components/DataModeBadge";
import { ScenarioSwitcher } from "./components/ScenarioSwitcher";
import { DashboardGrid } from "./layout/DashboardGrid";

export default function App() {
  const [mode, setMode] = useState<DataMode | null>(null);
  const [scenario, setScenario] = useState<string | undefined>(undefined);
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  // 모드를 알기 전에는 스냅샷을 요청하지 않는다. 시나리오를 붙일지 말지가
  // 모드에 달려 있고, 요청을 띄웠다가 취소하면 느린 실데이터 수집이 매번
  // 처음부터 다시 시작한다.
  const { snapshot, error, loading } = useSnapshot(scenario, mode !== null);

  useEffect(() => {
    const c = new AbortController();
    fetchInfo(c.signal)
      .then(async (info: ApiInfo) => {
        setMode(info.mode);
        // 시나리오는 MOCK 에서만 의미가 있다. 실데이터 모드에서 시나리오를
        // 보내면 무엇을 보고 있는지 화면이 거짓말을 한다.
        if (info.mode !== "MOCK") {
          setScenarios([]);
          return;
        }
        const rows = await fetchScenarios(c.signal);
        setScenarios(rows);
        setScenario((cur) => cur ?? rows.find((r) => r.is_active)?.name);
      })
      .catch(() => {
        // info 조차 실패하면 백엔드가 없는 것이다. 스냅샷을 시도해
        // 에러 배너가 이유를 말하게 한다.
        setMode("MOCK");
        setScenarios([]);
      });
    return () => c.abort();
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <strong>Market Pulse AI</strong>
          <span>Market Intelligence</span>
        </div>
        {mode === "MOCK" ? (
          <ScenarioSwitcher
            scenarios={scenarios}
            active={scenario ?? null}
            onSelect={setScenario}
          />
        ) : null}
        {snapshot ? (
          <DataModeBadge health={snapshot.data_health} scenario={snapshot.scenario} />
        ) : null}
      </header>

      {error ? (
        <div className="banner" role="alert">
          <span className="tag">연결 오류</span>
          <span>{error}</span>
          <span style={{ color: "var(--muted)" }}>
            {snapshot
              ? "아래 화면은 마지막으로 받은 데이터입니다."
              : "백엔드를 실행하세요: uvicorn marketpulse.api.main:app --reload"}
          </span>
        </div>
      ) : null}

      {snapshot ? (
        <DashboardGrid snapshot={snapshot} />
      ) : (
        <div className="grid">
          <section className="panel span-3">
            <div className="panel-body" style={{ color: "var(--muted)" }}>
              {loading
                ? mode === "MOCK" || mode === null
                  ? "스냅샷을 불러오는 중…"
                  : "실데이터를 수집하는 중… 첫 요청은 공급자 47곳을 도느라 오래 걸립니다."
                : "표시할 데이터가 없습니다."}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
