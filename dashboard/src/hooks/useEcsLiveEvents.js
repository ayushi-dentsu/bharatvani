import { useState, useEffect, useRef } from 'react';

// Helper to resolve ECS WebSocket URL
export function getEcsWebSocketUrl() {
  // 1. Query param
  const params = new URLSearchParams(window.location.search);
  const ecsIp = params.get('ecs_ip');
  if (ecsIp) return `ws://${ecsIp}:8080/ws`;
  // 2. Env var
  const envIp = process.env.REACT_APP_ECS_IP;
  if (envIp) return `ws://${envIp}:8080/ws`;
  // 3. Fallback
  return 'ws://localhost:8080/ws';
}

// Hook to connect to ECS WebSocket and update dashboard
export function useEcsLiveEvents() {
  const [screenings, setScreenings] = useState([]);
  const [metrics, setMetrics] = useState({
    total: 0,
    highRisk: 0,
    avgConfidence: 0,
  });
  const [connectionStatus, setConnectionStatus] = useState('disconnected'); // connected, reconnecting, disconnected
  const wsRef = useRef(null);
  const reconnectTimeout = useRef(null);

  // Calculate metrics
  const calculateMetrics = (data) => {
    const total = data.length;
    const highRisk = data.filter(s => s.combined_risk === 'HIGH').length;
    const avgConfidence = total ? (data.reduce((sum, s) => sum + s.confidence, 0) / total) : 0;
    return { total, highRisk, avgConfidence: Number(avgConfidence.toFixed(2)) };
  };

  // WebSocket connect/reconnect logic
  useEffect(() => {
    let isMounted = true;
    let ws;
    let reconnectAttempts = 0;
    const url = getEcsWebSocketUrl();

    function connect() {
      setConnectionStatus(reconnectAttempts === 0 ? 'connecting' : 'reconnecting');
      ws = new window.WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMounted) return;
        setConnectionStatus('connected');
        reconnectAttempts = 0;
      };

      ws.onmessage = (evt) => {
        if (!isMounted) return;
        try {
          const msg = JSON.parse(evt.data);
          if (msg.event === 'screening_completed') {
            setScreenings(prev => {
              const updated = [msg, ...prev];
              setMetrics(calculateMetrics(updated));
              return updated;
            });
          }
        } catch (e) {
          // Ignore bad messages
        }
      };

      ws.onclose = () => {
        if (!isMounted) return;
        setConnectionStatus('reconnecting');
        reconnectAttempts++;
        reconnectTimeout.current = setTimeout(connect, Math.min(5000, 1000 * reconnectAttempts));
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      isMounted = false;
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
    };
  }, []);

  return {
    screenings,
    metrics,
    connectionStatus,
  };
}