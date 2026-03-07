import React, { useMemo, useState } from 'react';
import { ComposableMap, Geographies, Geography, Marker } from 'react-simple-maps';
import SectionCard from './SectionCard';

const INDIA_GEO_URL =
  'https://raw.githubusercontent.com/deldersveld/topojson/master/countries/india/india-states.json';

export default function IndiaHeatmapSection({ stateHeat }) {
  const [activeState, setActiveState] = useState(null);

  const highestScreenings = useMemo(
    () => Math.max(...stateHeat.map((state) => state.screenings), 1),
    [stateHeat]
  );

  return (
    <SectionCard
      title="Rural India Heatmap"
      subtitle="State-wise screening hotspots"
      className="h-full"
    >
      <div className="relative">
        <div className="h-[360px] overflow-hidden rounded-xl bg-slate-50 p-2 ring-1 ring-slate-200">
          <ComposableMap projection="geoMercator" projectionConfig={{ center: [82.8, 22.5], scale: 920 }}>
            <Geographies geography={INDIA_GEO_URL}>
              {({ geographies }) =>
                geographies.map((geo) => (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill="#dbeafe"
                    stroke="#93c5fd"
                    strokeWidth={0.5}
                  />
                ))
              }
            </Geographies>

            {stateHeat.map((state) => {
              const intensity = state.screenings / highestScreenings;
              const radius = 7 + intensity * 12;
              const glow = state.screenings > highestScreenings * 0.8;
              const highRiskPercent = ((state.highRisk / state.screenings) * 100).toFixed(1);

              return (
                <Marker key={state.name} coordinates={state.coords}>
                  <g
                    onMouseEnter={() =>
                      setActiveState({
                        ...state,
                        highRiskPercent
                      })
                    }
                    onMouseLeave={() => setActiveState(null)}
                  >
                    <circle
                      r={radius}
                      fill={state.highRisk / state.screenings > 0.3 ? '#ef4444' : '#22c55e'}
                      fillOpacity={0.75}
                      stroke="#ffffff"
                      strokeWidth={2}
                      style={{
                        filter: glow ? 'drop-shadow(0 0 8px rgba(59,130,246,0.85))' : 'none'
                      }}
                    />
                  </g>
                </Marker>
              );
            })}
          </ComposableMap>
        </div>

        {activeState ? (
          <div className="absolute right-3 top-3 rounded-lg bg-slate-900/90 px-3 py-2 text-xs text-white shadow-lg">
            <p className="font-semibold">{activeState.name}</p>
            <p>Screenings: {activeState.screenings}</p>
            <p>High risk: {activeState.highRiskPercent}%</p>
          </div>
        ) : null}
      </div>
    </SectionCard>
  );
}
