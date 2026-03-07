import React, { useEffect, useMemo, useState } from 'react';
import AwsMetricsSection from './AwsMetricsSection';
import HeaderSection from './HeaderSection';
import IndiaHeatmapSection from './IndiaHeatmapSection';
import InferenceSection from './InferenceSection';
import LiveCallDemoSection from './LiveCallDemoSection';
import RecentScreeningsSection from './RecentScreeningsSection';
import RiskAnalyticsSection from './RiskAnalyticsSection';
import WaveformSection from './WaveformSection';
import {
  createInitialDashboardState,
  simulateDashboardTick
} from '../../services/mockDashboardData';

export default function WowDashboard() {
  const [dashboardState, setDashboardState] = useState(() => createInitialDashboardState());

  useEffect(() => {
    const intervalId = setInterval(() => {
      setDashboardState((previous) => simulateDashboardTick(previous));
    }, 5000);

    return () => clearInterval(intervalId);
  }, []);

  const lowRiskCount = useMemo(
    () => dashboardState.counters.totalScreenings - dashboardState.counters.highRiskDetected,
    [dashboardState.counters.totalScreenings, dashboardState.counters.highRiskDetected]
  );

  return (
    <div className="min-h-screen bg-slate-100 px-4 py-4 md:px-6 lg:px-8">
      <div className="mx-auto max-w-[1700px] space-y-4">
        <HeaderSection counters={dashboardState.counters} />

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <div className="xl:col-span-2">
            <LiveCallDemoSection
              stepIndex={dashboardState.flowStep}
              metrics={dashboardState.liveCallMetrics}
            />
          </div>
          <WaveformSection
            waveform={dashboardState.waveform}
            features={dashboardState.featureSet}
            status={dashboardState.status}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <div className="xl:col-span-1">
            <InferenceSection inference={dashboardState.inference} />
          </div>

          <div className="xl:col-span-2">
            <RiskAnalyticsSection
              highRisk={dashboardState.counters.highRiskDetected}
              lowRisk={lowRiskCount}
              screeningsPerHour={dashboardState.screeningsPerHour}
              languageUsage={dashboardState.languageUsage}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <div className="xl:col-span-2">
            <IndiaHeatmapSection stateHeat={dashboardState.stateHeat} />
          </div>
          <AwsMetricsSection awsMetrics={dashboardState.awsMetrics} />
        </div>

        <RecentScreeningsSection
          screenings={dashboardState.recentScreenings}
          searchTerm={dashboardState.searchTerm}
          onSearchChange={(searchTerm) =>
            setDashboardState((previous) => ({
              ...previous,
              searchTerm
            }))
          }
        />
      </div>
    </div>
  );
}
