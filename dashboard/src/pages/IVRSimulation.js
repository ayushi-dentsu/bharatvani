import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

const INPUT_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLE_RATE = 24000;
const BUFFER_SIZE = 4096;

function getEcsWsUrl() {
  const params = new URLSearchParams(window.location.search);
  const customIp = params.get('ecs_ip');
  if (customIp) return `ws://${customIp}:8080`;
  // Default: use CloudFront WSS proxy
  return process.env.REACT_APP_WS_URL || 'wss://d2uf59v9m9cg0y.cloudfront.net/ws';
}

// Audio helpers
function float32ToPcm16(f32) {
  const pcm = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return pcm;
}
function pcm16ToFloat32(pcm) {
  const f32 = new Float32Array(pcm.length);
  for (let i = 0; i < pcm.length; i++) f32[i] = pcm[i] / (pcm[i] < 0 ? 0x8000 : 0x7fff);
  return f32;
}
function base64ToPcm16(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Int16Array(bytes.buffer);
}
function ab2b64(buf) {
  const bytes = new Uint8Array(buf);
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

const PHASE = { IDLE: 'idle', INTAKE: 'intake', PROCESSING: 'processing', RESULTS: 'results' };

// Animated pulse ring component
function PulseRing({ color = 'blue', active = false }) {
  if (!active) return null;
  return (
    <span className="relative flex h-3 w-3">
      <span className={`animate-ping absolute inline-flex h-full w-full rounded-full bg-${color}-400 opacity-75`} />
      <span className={`relative inline-flex rounded-full h-3 w-3 bg-${color}-500`} />
    </span>
  );
}

// Waveform bars animation
function WaveformBars({ active }) {
  if (!active) return null;
  return (
    <div className="flex items-end gap-0.5 h-6">
      {[...Array(20)].map((_, i) => (
        <div
          key={i}
          className="w-1 bg-gradient-to-t from-emerald-500 to-emerald-300 rounded-full"
          style={{
            height: `${Math.random() * 100}%`,
            animation: `waveBar 0.5s ease-in-out ${i * 0.05}s infinite alternate`,
          }}
        />
      ))}
    </div>
  );
}

// Step indicator for processing
function ProcessingSteps({ step }) {
  const steps = [
    { icon: '🎤', label: 'Cough Analysis', desc: 'Analyzing audio patterns' },
    { icon: '🧬', label: 'Symptom Analysis', desc: 'Processing health data' },
    { icon: '🤖', label: 'AI Assessment', desc: 'Generating risk report' },
  ];
  return (
    <div className="flex items-center justify-center gap-2 mt-6">
      {steps.map((s, i) => (
        <React.Fragment key={i}>
          <div className={`flex flex-col items-center transition-all duration-500 ${
            i <= step ? 'opacity-100 scale-100' : 'opacity-30 scale-90'
          }`}>
            <div className={`w-14 h-14 rounded-2xl flex items-center justify-center text-2xl mb-2 transition-all duration-500 ${
              i < step ? 'bg-emerald-100 shadow-emerald-200 shadow-md' :
              i === step ? 'bg-blue-100 shadow-blue-200 shadow-lg animate-pulse' :
              'bg-gray-100'
            }`}>
              {i < step ? '✅' : s.icon}
            </div>
            <span className="text-xs font-medium text-gray-700">{s.label}</span>
            <span className="text-[10px] text-gray-400">{s.desc}</span>
          </div>
          {i < steps.length - 1 && (
            <div className={`w-12 h-0.5 mb-8 transition-all duration-500 ${
              i < step ? 'bg-emerald-400' : 'bg-gray-200'
            }`} />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

export default function IVRSimulation() {
  const navigate = useNavigate();
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [wsUrl, setWsUrl] = useState(getEcsWsUrl);
  const [phase, setPhase] = useState(PHASE.IDLE);
  const [messages, setMessages] = useState([]);
  const [stateLabel, setStateLabel] = useState('');
  const lastAssistant = useRef('');
  const lastUser = useRef('');
  const audioCtxRef = useRef(null);
  const micStreamRef = useRef(null);
  const scriptNodeRef = useRef(null);
  const playbackCtxRef = useRef(null);
  const nextPlayTimeRef = useRef(0);
  const [coughActive, setCoughActive] = useState(false);
  const [coughCountdown, setCoughCountdown] = useState(0);
  const [screeningId, setScreeningId] = useState(null);
  const [assessment, setAssessment] = useState(null);
  const [pollError, setPollError] = useState(null);
  const [processingStep, setProcessingStep] = useState(0);
  const transcriptRef = useRef(null);

  const addMsg = useCallback((role, text) => {
    if (role === 'assistant') { if (text === lastAssistant.current) return; lastAssistant.current = text; }
    else if (role === 'user') { if (text === lastUser.current) return; lastUser.current = text; }
    setMessages(prev => [...prev, { role, text, ts: Date.now() }]);
  }, []);

  useEffect(() => {
    if (transcriptRef.current) transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
  }, [messages]);

  // WebSocket
  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.onopen = () => { setConnected(true); addMsg('system', 'Connected to BharatVani server.'); };
    ws.onclose = () => { setConnected(false); stopMic(); };
    ws.onerror = () => addMsg('error', 'Connection failed. Check the server address.');
    ws.onmessage = (evt) => { try { handleMsg(JSON.parse(evt.data)); } catch {} };
  }, [wsUrl, addMsg]);

  const disconnect = useCallback(() => {
    stopMic();
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    setConnected(false);
  }, []);

  const handleMsg = useCallback((msg) => {
    switch (msg.type) {
      case 'audio': playAudio(msg.data); break;
      case 'transcript': addMsg(msg.role || 'assistant', msg.text); break;
      case 'state': setStateLabel(msg.question ? `${msg.state} — ${msg.question}` : msg.state || ''); break;
      case 'cough_start': startCoughOverlay(msg.duration || 8); break;
      case 'result': handleResult(msg); break;
      case 'error': addMsg('error', msg.message); break;
      default: break;
    }
  }, [addMsg]);

  const startConversation = async () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    setPhase(PHASE.INTAKE);
    setMessages([]);
    setAssessment(null);
    setScreeningId(null);
    setPollError(null);
    setProcessingStep(0);
    lastAssistant.current = '';
    lastUser.current = '';
    if (playbackCtxRef.current) playbackCtxRef.current.close();
    playbackCtxRef.current = new AudioContext({ sampleRate: OUTPUT_SAMPLE_RATE });
    nextPlayTimeRef.current = 0;
    await startMic();
    wsRef.current.send(JSON.stringify({ type: 'control', action: 'start' }));
    addMsg('system', 'Your health screening has started. Please speak when prompted.');
  };

  // Mic
  const startMic = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: INPUT_SAMPLE_RATE, channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      micStreamRef.current = stream;
      const ctx = new AudioContext({ sampleRate: INPUT_SAMPLE_RATE });
      audioCtxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const node = ctx.createScriptProcessor(BUFFER_SIZE, 1, 1);
      node.onaudioprocess = (e) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        const f32 = e.inputBuffer.getChannelData(0);
        const pcm = float32ToPcm16(f32);
        wsRef.current.send(JSON.stringify({ type: 'audio', data: ab2b64(pcm.buffer) }));
      };
      source.connect(node);
      node.connect(ctx.destination);
      scriptNodeRef.current = node;
    } catch (e) {
      addMsg('error', 'Microphone access denied: ' + e.message);
    }
  };
  const stopMic = () => {
    if (scriptNodeRef.current) { scriptNodeRef.current.disconnect(); scriptNodeRef.current = null; }
    if (audioCtxRef.current) { audioCtxRef.current.close(); audioCtxRef.current = null; }
    if (micStreamRef.current) { micStreamRef.current.getTracks().forEach(t => t.stop()); micStreamRef.current = null; }
  };

  // Playback
  const playAudio = (b64) => {
    const ctx = playbackCtxRef.current;
    if (!ctx) return;
    const pcm = base64ToPcm16(b64);
    const f32 = pcm16ToFloat32(pcm);
    const buf = ctx.createBuffer(1, f32.length, OUTPUT_SAMPLE_RATE);
    buf.getChannelData(0).set(f32);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    const now = ctx.currentTime;
    if (nextPlayTimeRef.current < now) nextPlayTimeRef.current = now;
    src.start(nextPlayTimeRef.current);
    nextPlayTimeRef.current += buf.duration;
  };

  // Cough overlay
  const startCoughOverlay = (duration) => {
      setCoughActive(true);
      setCoughCountdown(duration);

      // Collect PCM from the already-active mic (no new getUserMedia needed)
      const coughChunks = [];
      let recording = true;

      // Swap the scriptNode handler to collect cough audio instead of sending to Nova
      const origHandler = scriptNodeRef.current ? scriptNodeRef.current.onaudioprocess : null;
      if (scriptNodeRef.current) {
        scriptNodeRef.current.onaudioprocess = (e) => {
          if (!recording) return;
          const f32 = e.inputBuffer.getChannelData(0);
          coughChunks.push(float32ToPcm16(new Float32Array(f32)));
        };
      }

      // Play beep
      try {
        const beepCtx = new AudioContext();
        const osc = beepCtx.createOscillator();
        const gain = beepCtx.createGain();
        osc.frequency.value = 880;
        gain.gain.value = 0.3;
        osc.connect(gain);
        gain.connect(beepCtx.destination);
        osc.start();
        osc.stop(beepCtx.currentTime + 0.3);
        setTimeout(() => beepCtx.close(), 500);
      } catch (e) { /* ignore */ }

      const iv = setInterval(() => {
        setCoughCountdown(prev => {
          if (prev <= 1) {
            clearInterval(iv);
            recording = false;
            setCoughActive(false);

            // Restore original handler so mic resumes sending to Nova after cough phase
            if (scriptNodeRef.current) {
              scriptNodeRef.current.onaudioprocess = origHandler;
            }

            // Build WAV from collected PCM and send
            if (coughChunks.length > 0 && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
              const totalLen = coughChunks.reduce((s, c) => s + c.length, 0);
              const merged = new Int16Array(totalLen);
              let off = 0;
              for (const c of coughChunks) { merged.set(c, off); off += c.length; }

              const dataBytes = merged.length * 2;
              const wav = new ArrayBuffer(44 + dataBytes);
              const v = new DataView(wav);
              const ws = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
              ws(0, 'RIFF');
              v.setUint32(4, 36 + dataBytes, true);
              ws(8, 'WAVE');
              ws(12, 'fmt ');
              v.setUint32(16, 16, true);
              v.setUint16(20, 1, true);
              v.setUint16(22, 1, true);
              v.setUint32(24, INPUT_SAMPLE_RATE, true);
              v.setUint32(28, INPUT_SAMPLE_RATE * 2, true);
              v.setUint16(32, 2, true);
              v.setUint16(34, 16, true);
              ws(36, 'data');
              v.setUint32(40, dataBytes, true);
              for (let i = 0; i < merged.length; i++) v.setInt16(44 + i * 2, merged[i], true);

              wsRef.current.send(JSON.stringify({ type: 'cough_audio', data: ab2b64(wav) }));
              addMsg('system', 'Cough recording sent for analysis.');
            }
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    };

  // Result handling
  const handleResult = (msg) => {
      stopMic();
      const sid = msg?.screeningId || msg?.data?.screeningId || msg?.data?.screening_id;
      if (sid) {
        setScreeningId(sid);
        setPhase(PHASE.PROCESSING);
        addMsg('system', 'Intake complete. Analyzing your results...');
        pollForAssessment(sid);
      } else {
        addMsg('system', 'Intake complete.');
        setPhase(PHASE.RESULTS);
      }
    };

  const pollForAssessment = async (sid) => {
      const apiUrl = process.env.REACT_APP_SCREENING_API || 'https://o01ngd8pfe.execute-api.us-east-1.amazonaws.com/screening';
      // Pipeline can take ~2-3 min. Poll for up to 60 attempts × 5s = 5 minutes
      for (let i = 0; i < 60; i++) {
        if (i < 5) setProcessingStep(0);
        else if (i < 20) setProcessingStep(1);
        else setProcessingStep(2);
        try {
          const resp = await fetch(`${apiUrl}?screeningId=${encodeURIComponent(sid)}`);
          if (resp.ok) {
            const item = await resp.json();
            if (item && item.assessment) {
              setProcessingStep(3);
              await new Promise(r => setTimeout(r, 500));
              setAssessment(item.assessment);
              setPhase(PHASE.RESULTS);
              return;
            }
          }
        } catch {}
        await new Promise(r => setTimeout(r, 5000));
      }
      setPollError('Results are taking longer than expected. Your screening ID is: ' + sid);
      setPhase(PHASE.RESULTS);
    };

  useEffect(() => { return () => { disconnect(); }; }, [disconnect]);

  const riskColor = (l) => l === 'HIGH' ? 'red' : l === 'MEDIUM' ? 'amber' : 'emerald';
  const riskBg = (l) => `bg-${riskColor(l)}-50 border-${riskColor(l)}-200 text-${riskColor(l)}-700`;
  const riskIcon = (l) => l === 'HIGH' ? '🔴' : l === 'MEDIUM' ? '🟡' : '🟢';

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-950 to-indigo-950 text-white">
      {/* Decorative background elements */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl" />
        <div className="absolute top-1/2 -left-40 w-80 h-80 bg-indigo-500/10 rounded-full blur-3xl" />
        <div className="absolute -bottom-20 right-1/3 w-72 h-72 bg-emerald-500/10 rounded-full blur-3xl" />
      </div>

      {/* Header */}
      <div className="relative z-10 border-b border-white/10 backdrop-blur-sm bg-white/5">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-400 to-blue-500 flex items-center justify-center text-lg shadow-lg shadow-emerald-500/20">
              🩺
            </div>
            <div>
              <h1 className="text-lg font-bold bg-gradient-to-r from-white to-blue-200 bg-clip-text text-transparent">
                BharatVani
              </h1>
              <p className="text-[11px] text-blue-300/60">AI Health Screening System</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <PulseRing color={connected ? 'emerald' : 'gray'} active={connected} />
              {!connected && <span className="w-3 h-3 rounded-full bg-gray-500" />}
              <span className={`text-xs font-medium ${connected ? 'text-emerald-400' : 'text-gray-500'}`}>
                {connected ? 'Live' : 'Offline'}
              </span>
            </div>
            <button
              onClick={() => navigate('/admin-dashboard')}
              className="text-xs text-blue-400/70 hover:text-blue-300 transition"
            >
              Admin →
            </button>
          </div>
        </div>
      </div>

      <div className="relative z-10 max-w-3xl mx-auto px-4 py-8 space-y-6">

        {/* ─── IDLE ──────────────────────────────────────────────────── */}
        {phase === PHASE.IDLE && (
          <div className="space-y-6">
            {/* Hero */}
            <div className="text-center py-8">
              <div className="inline-flex items-center justify-center w-20 h-20 rounded-3xl bg-gradient-to-br from-emerald-400 to-blue-500 text-4xl mb-4 shadow-2xl shadow-emerald-500/30">
                🎤
              </div>
              <h2 className="text-3xl font-bold mb-2 bg-gradient-to-r from-white via-blue-100 to-emerald-200 bg-clip-text text-transparent">
                Voice Health Screening
              </h2>
              <p className="text-blue-300/60 text-sm max-w-md mx-auto">
                Answer a few questions by voice. Our AI will analyze your symptoms and provide a health risk assessment.
              </p>
            </div>

            {/* Connection card */}
            <div className="backdrop-blur-xl bg-white/5 border border-white/10 rounded-2xl p-6 shadow-2xl">
              <label className="text-xs text-blue-300/50 font-medium uppercase tracking-wider mb-2 block">
                Server Address
              </label>
              <div className="flex gap-2 mb-4">
                <input
                  type="text"
                  value={wsUrl}
                  onChange={e => setWsUrl(e.target.value)}
                  className="flex-1 px-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-sm text-white placeholder-white/20 focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 outline-none transition"
                  placeholder="ws://your-ecs-ip:8080"
                />
                {!connected ? (
                  <button onClick={connect} className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-xl text-sm font-medium transition shadow-lg shadow-blue-600/30">
                    Connect
                  </button>
                ) : (
                  <button onClick={disconnect} className="px-5 py-2.5 bg-red-500/80 hover:bg-red-500 rounded-xl text-sm font-medium transition">
                    Disconnect
                  </button>
                )}
              </div>

              {connected && (
                <button
                  onClick={startConversation}
                  className="w-full py-4 bg-gradient-to-r from-emerald-500 to-blue-500 hover:from-emerald-400 hover:to-blue-400 rounded-xl text-base font-bold transition shadow-xl shadow-emerald-500/20 flex items-center justify-center gap-2"
                >
                  <span className="text-xl">🎤</span> Start Health Screening
                </button>
              )}
            </div>

            {/* Feature cards */}
            <div className="grid grid-cols-3 gap-3">
              {[
                { icon: '🗣️', title: 'Voice-Based', desc: 'Speak naturally in Hindi or English' },
                { icon: '🤖', title: 'AI-Powered', desc: 'ML models analyze your health data' },
                { icon: '📊', title: 'Instant Results', desc: 'Get your risk assessment in seconds' },
              ].map(f => (
                <div key={f.title} className="backdrop-blur-xl bg-white/5 border border-white/10 rounded-xl p-4 text-center">
                  <div className="text-2xl mb-2">{f.icon}</div>
                  <div className="text-xs font-semibold text-white/80 mb-1">{f.title}</div>
                  <div className="text-[10px] text-blue-300/40">{f.desc}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ─── INTAKE ────────────────────────────────────────────────── */}
        {phase === PHASE.INTAKE && (
          <div className="backdrop-blur-xl bg-white/5 border border-white/10 rounded-2xl overflow-hidden shadow-2xl">
            {/* Status bar */}
            <div className="px-4 py-3 bg-white/5 border-b border-white/10 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <PulseRing color="emerald" active />
                <span className="text-xs font-medium text-emerald-400">Screening in progress</span>
              </div>
              {stateLabel && (
                <span className="text-xs text-blue-300/50 truncate max-w-[200px]">{stateLabel}</span>
              )}
            </div>

            {/* Transcript */}
            <div ref={transcriptRef} className="h-[420px] overflow-y-auto p-4 space-y-3">
              {messages.map((m, i) => (
                <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                    m.role === 'assistant'
                      ? 'bg-blue-500/20 text-blue-100 rounded-bl-md'
                      : m.role === 'user'
                      ? 'bg-emerald-500/20 text-emerald-100 rounded-br-md'
                      : m.role === 'error'
                      ? 'bg-red-500/20 text-red-300'
                      : 'bg-white/5 text-white/40 italic text-xs'
                  }`}>
                    {m.role === 'assistant' && <span className="text-blue-400 mr-1">🤖</span>}
                    {m.role === 'user' && <span className="text-emerald-400 mr-1">🗣️</span>}
                    {m.text}
                  </div>
                </div>
              ))}
            </div>

            {/* Bottom bar */}
            <div className="px-4 py-3 bg-white/5 border-t border-white/10 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <WaveformBars active={phase === PHASE.INTAKE} />
                <span className="text-xs text-white/30">Listening...</span>
              </div>
              <button
                onClick={() => { stopMic(); disconnect(); setPhase(PHASE.IDLE); }}
                className="px-4 py-1.5 bg-red-500/20 hover:bg-red-500/40 text-red-300 rounded-lg text-xs font-medium transition border border-red-500/20"
              >
                End Session
              </button>
            </div>
          </div>
        )}

        {/* ─── PROCESSING ────────────────────────────────────────────── */}
        {phase === PHASE.PROCESSING && (
          <div className="backdrop-blur-xl bg-white/5 border border-white/10 rounded-2xl p-8 shadow-2xl text-center">
            <div className="inline-flex items-center justify-center w-20 h-20 rounded-3xl bg-gradient-to-br from-blue-500 to-indigo-600 mb-4 shadow-2xl shadow-blue-500/30">
              <svg className="w-10 h-10 text-white animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            </div>
            <h2 className="text-xl font-bold mb-2 bg-gradient-to-r from-white to-blue-200 bg-clip-text text-transparent">
              Analyzing Your Screening
            </h2>
            <p className="text-sm text-blue-300/50 max-w-sm mx-auto mb-2">
              Our AI models are processing your voice recording and health information.
            </p>
            <ProcessingSteps step={processingStep} />
            {screeningId && (
              <p className="text-[10px] text-white/20 mt-6 font-mono">ID: {screeningId}</p>
            )}
          </div>
        )}

        {/* ─── RESULTS ───────────────────────────────────────────────── */}
        {phase === PHASE.RESULTS && (
          <div className="space-y-4">
            {pollError && !assessment && (
              <div className="backdrop-blur-xl bg-amber-500/10 border border-amber-500/20 rounded-2xl p-4 text-amber-300 text-sm">
                ⚠️ {pollError}
              </div>
            )}

            {assessment && (
              <>
                {/* Main risk card */}
                <div className={`backdrop-blur-xl rounded-2xl border-2 p-6 shadow-2xl ${
                  assessment.riskLevel === 'HIGH'
                    ? 'bg-red-500/10 border-red-500/30'
                    : assessment.riskLevel === 'MEDIUM'
                    ? 'bg-amber-500/10 border-amber-500/30'
                    : 'bg-emerald-500/10 border-emerald-500/30'
                }`}>
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div className={`w-14 h-14 rounded-2xl flex items-center justify-center text-2xl ${
                        assessment.riskLevel === 'HIGH' ? 'bg-red-500/20' :
                        assessment.riskLevel === 'MEDIUM' ? 'bg-amber-500/20' : 'bg-emerald-500/20'
                      }`}>
                        {riskIcon(assessment.riskLevel)}
                      </div>
                      <div>
                        <h2 className="text-2xl font-bold">{assessment.riskLevel} Risk</h2>
                        <p className="text-xs text-white/40">Health Risk Assessment</p>
                      </div>
                    </div>
                    <span className={`px-3 py-1.5 rounded-full text-xs font-bold ${
                      assessment.urgency === 'IMMEDIATE' ? 'bg-red-500/20 text-red-300 border border-red-500/30' :
                      assessment.urgency === 'SOON' ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' :
                      'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                    }`}>
                      {assessment.urgency}
                    </span>
                  </div>
                  <p className="text-sm text-white/70 leading-relaxed mb-4">{assessment.summary}</p>
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { label: 'Risk Score', value: `${assessment.riskScore}/100` },
                      { label: 'Confidence', value: `${assessment.confidence}%` },
                      { label: 'Follow-up', value: `${assessment.followUpDays} days` },
                    ].map(s => (
                      <div key={s.label} className="bg-white/5 rounded-xl p-3 text-center">
                        <div className="text-[10px] text-white/30 uppercase tracking-wider mb-1">{s.label}</div>
                        <div className="text-lg font-bold">{s.value}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Symptom breakdown */}
                {assessment.symptomBreakdown && (
                  <div className="backdrop-blur-xl bg-white/5 border border-white/10 rounded-2xl p-5">
                    <h3 className="font-semibold text-white/80 mb-3 text-sm">Risk Breakdown</h3>
                    <div className="grid grid-cols-3 gap-3">
                      {Object.entries(assessment.symptomBreakdown).map(([key, val]) => (
                        <div key={key} className={`rounded-xl p-3 text-center border ${
                          val === 'HIGH' ? 'bg-red-500/10 border-red-500/20' :
                          val === 'MEDIUM' ? 'bg-amber-500/10 border-amber-500/20' :
                          'bg-emerald-500/10 border-emerald-500/20'
                        }`}>
                          <div className="text-[10px] text-white/40 mb-1">
                            {key.replace(/([A-Z])/g, ' $1').replace(/^./, s => s.toUpperCase())}
                          </div>
                          <div className="text-sm font-bold flex items-center justify-center gap-1">
                            {riskIcon(val)} {val}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Key findings */}
                {assessment.keyFindings && (
                  <div className="backdrop-blur-xl bg-white/5 border border-white/10 rounded-2xl p-5">
                    <h3 className="font-semibold text-white/80 mb-3 text-sm">Key Findings</h3>
                    <div className="space-y-2">
                      {assessment.keyFindings.map((f, i) => (
                        <div key={i} className="flex items-start gap-2 text-sm text-white/60">
                          <span className="text-blue-400 mt-0.5 text-xs">●</span>
                          {f}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Recommendations */}
                {assessment.recommendations && (
                  <div className="backdrop-blur-xl bg-white/5 border border-white/10 rounded-2xl p-5">
                    <h3 className="font-semibold text-white/80 mb-3 text-sm">Recommendations</h3>
                    <div className="space-y-2">
                      {assessment.recommendations.map((r, i) => (
                        <div key={i} className="flex items-start gap-2 text-sm text-white/60">
                          <span className="text-emerald-400 mt-0.5">✓</span>
                          {r}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {assessment.referralNeeded && (
                  <div className="backdrop-blur-xl bg-red-500/10 border border-red-500/20 rounded-2xl p-4 text-red-300 text-sm font-medium flex items-center gap-2">
                    🏥 A referral to a healthcare provider is recommended. Please visit your nearest health center.
                  </div>
                )}
              </>
            )}

            {/* Actions */}
            <div className="flex gap-3 pt-2">
              <button
                onClick={() => { setPhase(PHASE.IDLE); setAssessment(null); setMessages([]); setScreeningId(null); setPollError(null); }}
                className="flex-1 py-3.5 bg-gradient-to-r from-emerald-500 to-blue-500 hover:from-emerald-400 hover:to-blue-400 rounded-xl font-semibold transition shadow-xl shadow-emerald-500/20"
              >
                Start New Screening
              </button>
              <button
                onClick={() => navigate('/admin-dashboard')}
                className="px-5 py-3.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl font-medium transition text-white/70"
              >
                All Screenings
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ─── Cough overlay ───────────────────────────────────────────── */}
      {coughActive && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center">
          <div className="bg-gradient-to-br from-slate-800 to-slate-900 border border-white/10 rounded-3xl p-10 text-center shadow-2xl max-w-sm">
            <div className="w-20 h-20 rounded-full bg-red-500/20 flex items-center justify-center text-4xl mx-auto mb-4 animate-pulse">
              🎤
            </div>
            <p className="text-lg font-bold text-white mb-1">Recording Cough</p>
            <p className="text-sm text-white/40 mb-6">Please cough 3 times clearly</p>
            <div className="text-6xl font-bold text-red-400 tabular-nums">{coughCountdown}</div>
          </div>
        </div>
      )}

      {/* Waveform animation keyframes */}
      <style>{`
        @keyframes waveBar {
          0% { height: 20%; }
          100% { height: 100%; }
        }
      `}</style>
    </div>
  );
}
