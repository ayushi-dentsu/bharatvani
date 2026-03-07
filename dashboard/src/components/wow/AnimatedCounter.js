import React from 'react';
import { AnimatePresence, motion } from 'framer-motion';

export default function AnimatedCounter({ label, value, suffix = '', tone = 'blue' }) {
  const toneClasses = {
    blue: 'text-blue-700',
    green: 'text-emerald-600',
    red: 'text-red-600'
  };

  return (
    <div className="rounded-xl bg-slate-50 px-4 py-3 ring-1 ring-slate-200">
      <p className="text-xs text-slate-500">{label}</p>
      <div className={`mt-2 text-2xl font-bold ${toneClasses[tone] || toneClasses.blue}`}>
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span
            key={`${label}-${value}`}
            initial={{ y: 10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -10, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="inline-block"
          >
            {value}
            {suffix}
          </motion.span>
        </AnimatePresence>
      </div>
    </div>
  );
}
