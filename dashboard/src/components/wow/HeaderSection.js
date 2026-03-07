import React from 'react';
import { Activity, PhoneCall, Zap } from 'lucide-react';
import AnimatedCounter from './AnimatedCounter';

function StatusChip({ icon: Icon, label, tone }) {
  const toneStyle = {
    green: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
    amber: 'bg-amber-50 text-amber-700 ring-amber-200',
    blue: 'bg-blue-50 text-blue-700 ring-blue-200'
  };

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold ring-1 ${
        toneStyle[tone] || toneStyle.blue
      }`}
    >
      <Icon size={14} />
      {label}
    </span>
  );
}

export default function HeaderSection({ counters }) {
  return (
    <section className="rounded-2xl bg-gradient-to-r from-blue-700 via-blue-600 to-cyan-600 p-6 text-white shadow-lg">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
            BharatVani – AI Voice Health Screening for Rural India
          </h1>
          <div className="mt-3 flex flex-wrap gap-2">
            <StatusChip icon={Activity} label="System Live" tone="green" />
            <StatusChip icon={Zap} label="AWS Lambda Active" tone="amber" />
            <StatusChip icon={PhoneCall} label="Amazon Connect IVR Running" tone="blue" />
          </div>
        </div>

        <div className="grid w-full grid-cols-2 gap-3 sm:grid-cols-3 xl:w-[58%] xl:grid-cols-5">
          <AnimatedCounter label="Total Screenings" value={counters.totalScreenings.toLocaleString()} />
          <AnimatedCounter label="High Risk Detected" value={counters.highRiskDetected.toLocaleString()} tone="red" />
          <AnimatedCounter label="Avg Confidence" value={counters.avgConfidence} suffix="%" tone="green" />
          <AnimatedCounter label="IVR Calls Today" value={counters.ivrCallsToday.toLocaleString()} />
          <AnimatedCounter label="SMS Notifications Sent" value={counters.smsSent.toLocaleString()} tone="green" />
        </div>
      </div>
    </section>
  );
}
