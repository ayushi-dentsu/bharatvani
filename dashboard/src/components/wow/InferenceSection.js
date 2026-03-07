import React from 'react';
import { motion } from 'framer-motion';
import { Brain } from 'lucide-react';
import SectionCard from './SectionCard';

function ProbabilityBar({ label, value }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-slate-600">
        <span>{label}</span>
        <span>{value}%</span>
      </div>
      <div className="h-3 overflow-hidden rounded-full bg-slate-100">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-400"
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ duration: 0.8 }}
        />
      </div>
    </div>
  );
}

export default function InferenceSection({ inference }) {
  return (
    <SectionCard
      title="AI Inference Visualization"
      subtitle="Model output probabilities"
      rightContent={<Brain size={16} className="text-blue-600" />}
      className="h-full"
    >
      <div className="space-y-4">
        <ProbabilityBar label="Respiratory Risk" value={inference.respiratoryRisk} />
        <ProbabilityBar label="Cardiac Pattern" value={inference.cardiacPattern} />
        <ProbabilityBar label="Speech Degradation" value={inference.speechDegradation} />
        <ProbabilityBar label="Mental Health Indicators" value={inference.mentalHealthIndicators} />

        <div className="mt-2 rounded-xl border border-slate-200 bg-slate-50 p-3">
          <p className="text-xs text-slate-500">Final Output</p>
          <div className="mt-1 flex items-center justify-between">
            <span
              className={`text-sm font-bold ${
                inference.riskLevel === 'HIGH' ? 'text-red-600' : 'text-emerald-600'
              }`}
            >
              Risk Level: {inference.riskLevel}
            </span>
            <span className="text-sm font-bold text-slate-900">
              Confidence: {inference.confidenceScore}%
            </span>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}
