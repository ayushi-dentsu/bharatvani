import React, { useMemo } from 'react';
import { Search } from 'lucide-react';
import SectionCard from './SectionCard';

const riskBadgeClasses = {
  HIGH: 'bg-red-50 text-red-700 ring-red-200',
  LOW: 'bg-emerald-50 text-emerald-700 ring-emerald-200'
};

export default function RecentScreeningsSection({ screenings, searchTerm, onSearchChange }) {
  const filteredScreenings = useMemo(() => {
    const value = searchTerm.trim().toLowerCase();

    if (!value) return screenings;

    return screenings.filter(
      (screening) =>
        screening.id.toLowerCase().includes(value) ||
        screening.phone.toLowerCase().includes(value) ||
        screening.language.toLowerCase().includes(value)
    );
  }, [screenings, searchTerm]);

  return (
    <SectionCard title="Recent Screenings" subtitle="Latest real-time screening outcomes" className="h-full">
      <div className="space-y-4">
        <label className="relative block">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={searchTerm}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search by ID, phone or language"
            className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm outline-none ring-blue-300 transition focus:ring"
          />
        </label>

        <div className="overflow-x-auto rounded-xl ring-1 ring-slate-200">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                <th className="px-3 py-2">ID</th>
                <th className="px-3 py-2">Phone</th>
                <th className="px-3 py-2">Language</th>
                <th className="px-3 py-2">Risk Level</th>
                <th className="px-3 py-2">Confidence</th>
                <th className="px-3 py-2">Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white text-sm text-slate-700">
              {filteredScreenings.map((screening) => (
                <tr key={screening.id} className="transition hover:bg-slate-50">
                  <td className="whitespace-nowrap px-3 py-2 font-medium text-slate-900">{screening.id}</td>
                  <td className="whitespace-nowrap px-3 py-2">{screening.phone}</td>
                  <td className="whitespace-nowrap px-3 py-2">{screening.language}</td>
                  <td className="whitespace-nowrap px-3 py-2">
                    <span
                      className={`rounded-full px-2 py-1 text-xs font-semibold ring-1 ${
                        riskBadgeClasses[screening.riskLevel] || riskBadgeClasses.LOW
                      }`}
                    >
                      {screening.riskLevel === 'HIGH' ? 'High Risk' : 'Low Risk'}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2">{screening.confidence}%</td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-500">{screening.timestamp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </SectionCard>
  );
}
