import React from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';
import SectionCard from './SectionCard';

const riskColors = ['#ef4444', '#22c55e'];
const languageColors = ['#2563eb', '#10b981'];

export default function RiskAnalyticsSection({ highRisk, lowRisk, screeningsPerHour, languageUsage }) {
  const riskDistribution = [
    { name: 'High Risk', value: highRisk },
    { name: 'Low Risk', value: lowRisk }
  ];

  return (
    <SectionCard title="Risk Analytics" subtitle="Live risk trends and language split" className="h-full">
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="h-56 rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200">
          <p className="mb-2 text-xs font-semibold text-slate-600">High Risk vs Low Risk</p>
          <ResponsiveContainer width="100%" height="85%">
            <BarChart data={riskDistribution}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                {riskDistribution.map((entry, index) => (
                  <Cell key={entry.name} fill={riskColors[index]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="h-56 rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200">
          <p className="mb-2 text-xs font-semibold text-slate-600">Screenings per Hour</p>
          <ResponsiveContainer width="100%" height="85%">
            <LineChart data={screeningsPerHour}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="time" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Line
                type="monotone"
                dataKey="screenings"
                stroke="#2563eb"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="h-56 rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200">
          <p className="mb-2 text-xs font-semibold text-slate-600">Language Usage</p>
          <ResponsiveContainer width="100%" height="85%">
            <PieChart>
              <Pie
                data={languageUsage}
                cx="50%"
                cy="50%"
                outerRadius={75}
                dataKey="value"
                label={({ name, value }) => `${name} ${value}%`}
                labelLine={false}
              >
                {languageUsage.map((entry, index) => (
                  <Cell key={entry.name} fill={languageColors[index % languageColors.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </SectionCard>
  );
}
