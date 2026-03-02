import React, { useState, useEffect } from 'react';
import { getRecentScreenings, getScreeningStats } from '../services/dynamoService';
import { getLambdaMetrics } from '../services/lambdaService';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

export default function Dashboard() {
  const [screenings, setScreenings] = useState([]);
  const [stats, setStats] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      const [screeningsData, statsData, metricsData] = await Promise.all([
        getRecentScreenings(20),
        getScreeningStats(),
        getLambdaMetrics()
      ]);
      
      setScreenings(screeningsData);
      setStats(statsData);
      setMetrics(metricsData);
      setLoading(false);
    } catch (error) {
      console.error('Error loading data:', error);
      setLoading(false);
    }
  };

  if (loading) return <div className="loading">Loading dashboard...</div>;

  const chartData = [
    { name: 'High Risk', value: stats?.highRisk || 0 },
    { name: 'Low Risk', value: stats?.lowRisk || 0 }
  ];

  return (
    <div className="dashboard">
      <h1>BharatVani Live Dashboard</h1>
      
      <div className="stats-grid">
        <div className="stat-card">
          <h3>Total Screenings</h3>
          <p className="stat-value">{stats?.total || 0}</p>
        </div>
        <div className="stat-card">
          <h3>High Risk</h3>
          <p className="stat-value risk-high">{stats?.highRisk || 0}</p>
        </div>
        <div className="stat-card">
          <h3>Avg Confidence</h3>
          <p className="stat-value">{stats?.avgConfidence || 0}%</p>
        </div>
        <div className="stat-card">
          <h3>Lambda Invocations</h3>
          <p className="stat-value">{metrics?.invocations || 0}</p>
        </div>
      </div>

      <div className="chart-container">
        <h2>Risk Distribution</h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData}>
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="value" fill="#FF9900" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="screenings-table">
        <h2>Recent Screenings</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Phone</th>
              <th>Risk Level</th>
              <th>Confidence</th>
              <th>Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {screenings.map(s => (
              <tr key={s.screeningId}>
                <td>{s.screeningId?.substring(0, 8)}</td>
                <td>{s.phoneNumber}</td>
                <td className={`risk-${s.riskLevel?.toLowerCase()}`}>{s.riskLevel}</td>
                <td>{s.confidence}%</td>
                <td>{new Date(s.timestamp).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
