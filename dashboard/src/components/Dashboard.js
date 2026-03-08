export default function Dashboard() {
  const {
    screenings: ecsScreenings,
    metrics: ecsMetrics,
    connectionStatus,
  } = useEcsLiveEvents();

  // Risk Distribution chart data
  const riskCounts = ecsScreenings.reduce((acc, s) => {
    acc[s.combined_risk] = (acc[s.combined_risk] || 0) + 1;
    return acc;
  }, {});

  // Screenings per hour chart data
  const hourCounts = {};
  ecsScreenings.forEach(s => {
    const hour = new Date(s.timestamp).getHours();
    hourCounts[hour] = (hourCounts[hour] || 0) + 1;
  });

  return (
    <div className="dashboard">
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '1rem' }}>
        <h1 style={{ flex: 1 }}>BharatVani Live Dashboard</h1>
        <span style={{ fontWeight: 'bold', color: connectionStatus === 'connected' ? '#2e7d32' : connectionStatus === 'reconnecting' ? '#ff9800' : '#c62828' }}>
          {connectionStatus === 'connected' && 'Connected to ECS'}
          {connectionStatus === 'reconnecting' && 'Reconnecting...'}
          {connectionStatus === 'disconnected' && 'Disconnected'}
        </span>
        <button
          className="ml-4 px-4 py-2 bg-blue-600 text-white rounded-xl shadow hover:bg-blue-700"
          onClick={() => window.location.href = '/ivr-simulation'}
        >
          Start IVR Simulation
        </button>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <h3>Total Screenings</h3>
          <p className="stat-value">{ecsMetrics.total}</p>
        </div>
        <div className="stat-card">
          <h3>High Risk</h3>
          <p className="stat-value risk-high">{ecsMetrics.highRisk}</p>
        </div>
        <div className="stat-card">
          <h3>Avg Confidence</h3>
          <p className="stat-value">{ecsMetrics.avgConfidence}%</p>
        </div>
      </div>

      <div className="chart-container">
        <h2>Risk Distribution</h2>
        <div style={{ display: 'flex', gap: '1rem' }}>
          {Object.entries(riskCounts).map(([risk, count]) => (
            <div key={risk}>{risk}: {count}</div>
          ))}
        </div>
      </div>

      <div className="chart-container">
        <h2>Screenings per Hour</h2>
        <div style={{ display: 'flex', gap: '1rem' }}>
          {Object.entries(hourCounts).map(([hour, count]) => (
            <div key={hour}>{hour}:00 - {count}</div>
          ))}
        </div>
      </div>

      <div className="screenings-table">
        <h2>Recent Screenings</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Phone</th>
              <th>Audio Risk</th>
              <th>Symptom Risk</th>
              <th>Combined Risk</th>
              <th>Confidence</th>
              <th>Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {ecsScreenings.map(s => (
              <tr key={s.screening_id}>
                <td>{s.screening_id}</td>
                <td>{s.phone}</td>
                <td>{s.audio_risk}</td>
                <td>{s.symptom_risk}</td>
                <td>{s.combined_risk}</td>
                <td>{s.confidence}</td>
                <td>{new Date(s.timestamp).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
