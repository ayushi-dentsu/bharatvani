import React from 'react';
import { motion } from 'framer-motion';
import { Brain, Mail, Mic, PhoneCall, Zap } from 'lucide-react';
import SectionCard from './SectionCard';

const flowSteps = [
  { icon: PhoneCall, title: 'Incoming Call' },
  { icon: Mic, title: 'Recording Cough' },
  { icon: Zap, title: 'Lambda ML Processing' },
  { icon: Brain, title: 'AI Risk Analysis' },
  { icon: Mail, title: 'SMS Sent' }
];

function Metric({ label, value, suffix = '' }) {
  return (
    <div className="rounded-xl bg-slate-50 px-3 py-2 ring-1 ring-slate-200">
      <p className="text-[11px] text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-bold text-slate-900">
        {value}
        {suffix}
      </p>
    </div>
  );
}

export default function LiveCallDemoSection({ stepIndex, metrics }) {
  return (
    <SectionCard
      title="Live Call Demo"
      subtitle="Hackathon WOW feature"
      className="h-full"
    >
      <div className="space-y-5">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-5">
          {flowSteps.map((step, index) => {
            const active = stepIndex === index;
            const completed = stepIndex > index;
            const Icon = step.icon;

            return (
              <div key={step.title} className="relative rounded-xl border border-slate-200 bg-white p-3">
                <motion.div
                  animate={
                    active
                      ? { scale: [1, 1.08, 1], boxShadow: ['0 0 0 rgba(37,99,235,0)', '0 0 18px rgba(37,99,235,0.45)', '0 0 0 rgba(37,99,235,0)'] }
                      : { scale: 1 }
                  }
                  transition={{ duration: 1.1, repeat: active ? Infinity : 0 }}
                  className={`mx-auto flex h-10 w-10 items-center justify-center rounded-full ${
                    active
                      ? 'bg-blue-600 text-white'
                      : completed
                        ? 'bg-emerald-500 text-white'
                        : 'bg-slate-100 text-slate-500'
                  }`}
                >
                  <Icon size={18} />
                </motion.div>
                <p className="mt-2 text-center text-xs font-semibold text-slate-700">{step.title}</p>
              </div>
            );
          })}
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Metric label="Calls Received" value={metrics.callsReceived.toLocaleString()} />
          <Metric label="Audio Processed" value={metrics.audioProcessed.toLocaleString()} />
          <Metric label="Inference Time" value={metrics.inferenceTimeMs} suffix=" ms" />
          <Metric label="SMS Delivery Rate" value={metrics.smsDeliveryRate.toFixed(1)} suffix="%" />
        </div>
      </div>
    </SectionCard>
  );
}
