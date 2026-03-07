import React from 'react';
import { motion } from 'framer-motion';
import { AudioWaveform } from 'lucide-react';
import SectionCard from './SectionCard';

export default function WaveformSection({ waveform, features, status }) {
  return (
    <SectionCard
      title="Voice Waveform Visualization"
      subtitle="Real-time cough recording"
      rightContent={<AudioWaveform size={16} className="text-blue-600" />}
      className="h-full"
    >
      <div className="space-y-4">
        <div className="flex h-32 items-end gap-1 overflow-hidden rounded-xl bg-slate-900 px-2 py-2">
          {waveform.map((barHeight, index) => (
            <motion.div
              key={`${index}-${barHeight}`}
              className="w-2 rounded-t bg-gradient-to-t from-cyan-400 to-blue-500"
              initial={{ height: 8 }}
              animate={{ height: Math.max(8, barHeight) }}
              transition={{ duration: 0.35 }}
            />
          ))}
        </div>

        <div className="flex flex-wrap gap-2">
          {features.map((feature) => (
            <span
              key={feature}
              className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700 ring-1 ring-blue-200"
            >
              {feature}
            </span>
          ))}
        </div>

        <p className="text-xs font-semibold text-emerald-600">{status}</p>
      </div>
    </SectionCard>
  );
}
