import { useEffect, useState } from "react";
import { fetchNews, fetchScenarios } from "./api/client";
import type { RawNewsItem, ScenarioInfo } from "./api/types";
import { useSnapshot } from "./api/useSnapshot";
import { DataModeBadge } from "./components/DataModeBadge";
import { ScenarioSwitcher } from "./components/ScenarioSwitcher";
import { DashboardGrid } from "./layout/DashboardGrid";

export default function App() {
  const [scenario, setScenario] = useState<string | undefined>(undefined);
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [news, setNews] = useState<RawNewsItem[]>([]);
  const { snapshot, error, loading } = useSnapshot(scenario);

  useEffect(() => {
    const c = new AbortController();
    fetchScenarios(c.signal)
      .then((rows) => {
        setScenarios(rows);
        setScenario((cur) => cur ?? rows.find((r) => r.is_active)?.name);
      })
      .catch(() => setScenarios([]));
    return () => c.abort();
  }, []);

  useEffect(() => {
    const c = new AbortController();
    fetchNews(scenario, c.signal)
      .then(setNews)
      .catch(() => setNews([]));
    return () => c.abort();
  }, [scenario, snapshot?.as_of]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <strong>Market Pulse AI</strong>
          <span>Market Intelligence</span>
        </div>
        <ScenarioSwitcher
          scenarios={scenarios}
          active={scenario ?? null}
          onSelect={setScenario}
        />
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
        <DashboardGrid snapshot={snapshot} news={news} />
      ) : (
        <div className="grid">
          <section className="panel span-3">
            <div className="panel-body" style={{ color: "var(--muted)" }}>
              {loading ? "스냅샷을 불러오는 중…" : "표시할 데이터가 없습니다."}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
