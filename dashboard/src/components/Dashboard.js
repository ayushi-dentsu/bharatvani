import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { getRecentScreenings } from '../services/dynamoService';

export default function Dashboard() {
  const navigate = useNavigate();
  const [screenings, setScreenings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const items = await getRecentScreenings(100);
      // Sort by timestamp descending
      items.sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''));
      setScreenings(items);
      setError(null);
    } catch (e) {
      setError('Failed to load screenings: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const iv = setInterval(fetchData, 10000); // poll every 10s
    return () => clearInterval(iv);
  }, [fetchData]);

  // Metrics
  const total = screenings.length;
  const completed = screenings.filter(s => s.assessment).length;
  const highRisk = screenings.filter(s => s.riskLevel === 'HIGH').length;
  const medRisk = screenings.filter(s => s.riskLevel === 'MEDIUM').length;
  const lowRisk = screenings.filter(s => s.riskLevel === 'LOW').length;

  const riskBadge = (level) => {
    if (level === 'HIGH') return 'bg-red-100 text-red-700';
    if (level === 'MEDIUM') return 'bg-amber-100 text-amber-700';
    if (level === 'LOW') return 'bg-green-100 text-green-700';
    return 'bg-gray-100 text-gray-500';
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <h1 className="text-xl font-bold text-gray-900">BharatVani Admin Dashboard</h1>
          <div className="flex gap-3">
            <button onClick={fetchData} className="text-sm text-gray-500 hover:text-gray-700">↻ Refresh</button>
            <button
              onClick={() => navigate('/ivr-simulation')}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
            >
              Start IVR Screening
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {[
            { label: 'Total', value: total, color: 'text-gray-900' },
            { label: 'Completed', value: completed, color: 'text-blue-600' },
            { label: 'High Risk', value: highRisk, color: 'text-red-600' },
            { label: 'Medium Risk', value: medRisk, color: 'text-amber-600' },
            { label: 'Low Risk', value: lowRisk, color: 'text-green-600' },
          ].map(s => (
            <div key={s.label} className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
              <div className="text-xs text-gray-500 mb-1">{s.label}</div>
              <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
            </div>
          ))}
        </div>

        {error && <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-red-700 text-sm">{error}</div>}

        {/* Screenings table */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200">
            <h2 className="font-semibold text-gray-800">Recent Screenings</h2>
          </div>
          {loading ? (
            <div className="p-8 text-center text-gray-400">Loading...</div>
          ) : screenings.length === 0 ? (
            <div className="p-8 text-center text-gray-400">No screenings yet</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                  <tr>
                    <th className="px-4 py-3 text-left">Patient</th>
                    <th className="px-4 py-3 text-left">Age/Gender</th>
                    <th className="px-4 py-3 text-left">Risk Level</th>
                    <th className="px-4 py-3 text-left">Urgency</th>
                    <th className="px-4 py-3 text-left">Summary</th>
                    <th className="px-4 py-3 text-left">Status</th>
                    <th className="px-4 py-3 text-left">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {screenings.map(s => (
                    <tr key={s.screeningId} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-900">
                        {s.patientName || 'Unknown'}
                      </td>
                      <td className="px-4 py-3 text-gray-600">
                        {s.age || '—'} / {s.gender || '—'}
                      </td>
                      <td className="px-4 py-3">
                        {s.riskLevel ? (
                          <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${riskBadge(s.riskLevel)}`}>
                            {s.riskLevel}
                          </span>
                        ) : <span className="text-gray-400">—</span>}
                      </td>
                      <td className="px-4 py-3 text-gray-600">{s.urgency || '—'}</td>
                      <td className="px-4 py-3 text-gray-600 max-w-xs truncate">{s.summary || '—'}</td>
                      <td className="px-4 py-3">
                        {s.assessment ? (
                          <span className="text-green-600 text-xs font-medium">Complete</span>
                        ) : (
                          <span className="text-amber-500 text-xs font-medium">{s.status || 'Pending'}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-500 text-xs">
                        {s.timestamp ? new Date(s.timestamp).toLocaleString() : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
