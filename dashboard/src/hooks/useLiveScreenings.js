import { useState, useEffect, useRef } from 'react';

const MOCK_API = [
  {
    id: 'scr_101',
    phone: '+91xxxx',
    language: 'Hindi',
    risk_level: 'HIGH',
    confidence: 0.82,
    timestamp: '2026-03-07T10:20:00Z',
    status: 'SMS_SENT',
  },
  {
    id: 'scr_100',
    phone: '+91xxxx',
    language: 'English',
    risk_level: 'LOW',
    confidence: 0.45,
    timestamp: '2026-03-07T09:50:00Z',
    status: 'RISK_CALCULATED',
  },
];

function useLiveScreenings({ pollInterval = 5000, apiUrl = '/api/screenings' } = {}) {
  const [screenings, setScreenings] = useState([]);
  const [metrics, setMetrics] = useState({
    total: 0,
    highRisk: 0,
    avgConfidence: 0,
  });
  const [newScreeningId, setNewScreeningId] = useState(null);
  const [liveEvent, setLiveEvent] = useState(null);
  const pollingRef = useRef();

  // Helper: Calculate metrics
  const calculateMetrics = (data) => {
    const total = data.length;
    const highRisk = data.filter(s => s.risk_level === 'HIGH').length;
    const avgConfidence = total ? (data.reduce((sum, s) => sum + s.confidence, 0) / total) : 0;
    return { total, highRisk, avgConfidence: Number(avgConfidence.toFixed(2)) };
  };

  // Helper: Detect new screening
  const detectNewScreening = (oldList, newList) => {
    if (!oldList.length) return null;
    const oldIds = new Set(oldList.map(s => s.id));
    const newItem = newList.find(s => !oldIds.has(s.id));
    return newItem ? newItem.id : null;
  };

  // Helper: Simulate API fetch
  const fetchScreenings = async () => {
    try {
      const res = await fetch(apiUrl);
      if (!res.ok) throw new Error('API unavailable');
      return await res.json();
    } catch (e) {
      // Fallback to mock data
      return MOCK_API;
    }
  };

  useEffect(() => {
    let mounted = true;
    const poll = async () => {
      const data = await fetchScreenings();
      if (!mounted) return;
      setMetrics(calculateMetrics(data));
      setScreenings(prev => {
        // Insert new at top, highlight
        const newId = detectNewScreening(prev, data);
        if (newId) setNewScreeningId(newId);
        return data;
      });
      // Simulate live event panel
      if (data.length && data[0].status) setLiveEvent(data[0].status);
    };
    poll();
    pollingRef.current = setInterval(poll, pollInterval);
    return () => {
      mounted = false;
      clearInterval(pollingRef.current);
    };
  }, [pollInterval, apiUrl]);

  // Clear highlight after 3s
  useEffect(() => {
    if (!newScreeningId) return;
    const timer = setTimeout(() => setNewScreeningId(null), 3000);
    return () => clearTimeout(timer);
  }, [newScreeningId]);

  return {
    screenings,
    metrics,
    newScreeningId,
    liveEvent,
  };
}

export default useLiveScreenings;