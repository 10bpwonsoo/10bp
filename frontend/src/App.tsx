import { useEffect, useState } from "react";
import { fetchInfo, fetchScenarios, staticBundle } from "./api/client";
import type { ApiInfo, DataMode, ScenarioInfo } from "./api/types";
import { useSnapshot } from "./api/useSnapshot";
import { useStateHistory } from "./api/useStateHistory";
import { useScenarioChecks } from "./api/useScenarioChecks";
import { DataModeBadge } from "./components/DataModeBadge";
import { RefreshButton } from "./components/RefreshButton";
import { ScenarioSwitcher } from "./components/ScenarioSwitcher";
import { scoreColor } from "./components/ScenarioCheckPanel";
import { ScenarioView } from "./components/ScenarioView";
import { useInvestment } from "./api/useInvestment";
import { DashboardGrid } from "./layout/DashboardGrid";
import { InvestmentSection } from "./investment/InvestmentSection";

export default function App() {
  const [mode, setMode] = useState<DataMode | null>(null);
  const [scenario, setScenario] = useState<string | undefined>(undefined);
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  // 모드를 알기 전에는 스냅샷을 요청하지 않는다. 시나리오를 붙일지 말지가
  // 모드에 달려 있고, 요청을 띄웠다가 취소하면 느린 실데이터 수집이 매번
  // 처음부터 다시 시작한다.
  const { snapshot, error, loading, lastUpdated, refreshNow, refreshing } = useSnapshot(
    scenario,
    mode !== null,
  );
  const bundle = staticBundle();
  // Market State 한 달 히스토리 — 스냅샷 as_of 가 바뀔 때만 다시 받는다.
  const { history: stateHistory } = useStateHistory(scenario, snapshot?.as_of ?? null, mode !== null);
  // 시나리오 점검 — 모의 탭을 실데이터로 바꾼 것. 데이터를 바꾸지 않고 '지금 시장이 그 시나리오와 얼마나 닮았나' 를 위에 붙인다.
  const { checks } = useScenarioChecks(scenario, snapshot?.as_of ?? null, mode !== null);
  const [checkName, setCheckName] = useState<string | null>(null);
  const activeCheck = checkName ? checks.find((c) => c.name === checkName) ?? null : null;
  // 시나리오 탭의 반도체·원자재 패널용. 실데이터 탭의 Investment 영역은 자기 훅을 그대로 쓴다.
  const { data: investmentForView } = useInvestment(scenario, mode !== null && activeCheck !== null);

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
        {checks.length > 0 ? (
          <div className="sc-tabs" role="group" aria-label="시나리오 점검" data-testid="scenario-tabs">
            <button type="button" className="sc-tab mono" aria-pressed={checkName === null} onClick={() => setCheckName(null)}>
              {mode === "MOCK" ? "판정만" : "실데이터"}
            </button>
            {checks.map((c) => (
              <button key={c.name} type="button" className="sc-tab mono" aria-pressed={checkName === c.name} onClick={() => setCheckName(c.name)} title={c.description}>
                {c.title.split(" — ")[0]}
                <span className="num" style={{ color: scoreColor(c.match_score) }}>{c.match_score.toFixed(0)}%</span>
              </button>
            ))}
          </div>
        ) : null}
        {snapshot ? (
          <DataModeBadge health={snapshot.data_health} scenario={snapshot.scenario} />
        ) : null}
        <RefreshButton
          onClick={refreshNow}
          busy={refreshing}
          lastUpdated={lastUpdated}
          mode={mode}
          staticNote={bundle?.collected ?? null}
        />
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
        <>
          {activeCheck ? (
            /* 시나리오 탭 — 실데이터 화면을 복제하지 않는다. 그 탭에 어울리는 판정만. */
            <ScenarioView check={activeCheck} snapshot={snapshot} history={stateHistory} investment={investmentForView} />
          ) : (
            <>
              <DashboardGrid snapshot={snapshot} history={stateHistory} />
              {/* 기존 대시보드 아래의 신규 영역. 별도 엔드포인트·캐시라 기존 화면이 먼저 뜬다. */}
              <InvestmentSection scenario={scenario} enabled={mode !== null} />
            </>
          )}
        </>
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
