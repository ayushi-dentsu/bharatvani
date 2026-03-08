import React, { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Phone, Mic, Brain, Lightning, Mail, ArrowLeft, ArrowRight, Play, Pause, Trash, Circle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const CALL_STAGES = [
  { key: 'incoming', label: 'Incoming Call', icon: <Phone /> },
  { key: 'recording', label: 'Recording Cough', icon: <Mic /> },
  { key: 'processing', label: 'Lambda ML Processing', icon: <Lightning /> },
  { key: 'analysis', label: 'AI Risk Analysis', icon: <Brain /> },
  { key: 'sms', label: 'SMS Sent', icon: <Mail /> },
];

const CALL_STATUS_MAP = {
  disconnected: { color: 'red', label: 'Disconnected', icon: <Circle className="text-red-500" /> },
  connecting: { color: 'yellow', label: 'Connecting', icon: <Circle className="text-yellow-500" /> },
  connected: { color: 'green', label: 'Connected', icon: <Circle className="text-green-500" /> },
  recording: { color: 'blue', label: 'Recording', icon: <Mic className="text-blue-500" /> },
  processing: { color: 'purple', label: 'Processing', icon: <Brain className="text-purple-500" /> },
  completed: { color: 'gray', label: 'Completed', icon: <Mail className="text-gray-500" /> },
};

function randomRisk() {
  return Math.random() > 0.5 ? 'HIGH' : 'LOW';
}

function randomConfidence() {
  return (0.7 + Math.random() * 0.25).toFixed(2);
}

export default function IVRSimulation() {
  const navigate = useNavigate();
  const [callStatus, setCallStatus] = useState('disconnected');
  const [stageIdx, setStageIdx] = useState(0);
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState(null);
  const [recordingTime, setRecordingTime] = useState(0);
  const [processingStage, setProcessingStage] = useState(null);
  const [screeningResult, setScreeningResult] = useState(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const timerRef = useRef(null);

  // Navigation
  const goBack = () => navigate('/admin-dashboard');

  // Call connect/disconnect
  const connectCall = () => {
    setCallStatus('connecting');
    setTimeout(() => {
      setCallStatus('connected');
      setStageIdx(0);
    }, 1000);
  };
  const disconnectCall = () => {
    setCallStatus('disconnected');
    setStageIdx(0);
    setIsRecording(false);
    setAudioBlob(null);
    setProcessingStage(null);
    setScreeningResult(null);
  };

  // Recording
  const startRecording = async () => {
    setCallStatus('recording');
    setStageIdx(1);
    setIsRecording(true);
    setRecordingTime(0);
    audioChunksRef.current = [];
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorderRef.current = new window.MediaRecorder(stream);
    mediaRecorderRef.current.ondataavailable = e => {
      if (e.data.size > 0) audioChunksRef.current.push(e.data);
    };
    mediaRecorderRef.current.onstop = () => {
      const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
      setAudioBlob(blob);
      stream.getTracks().forEach(track => track.stop());
    };
    mediaRecorderRef.current.start();
    timerRef.current = setInterval(() => setRecordingTime(t => t + 1), 1000);
  };
  const stopRecording = () => {
    setIsRecording(false);
    setCallStatus('connected');
    setStageIdx(2);
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    clearInterval(timerRef.current);
  };
  const deleteRecording = () => {
    setAudioBlob(null);
    setRecordingTime(0);
  };

  // Audio preview
  const [audioUrl, setAudioUrl] = useState(null);
  useEffect(() => {
    if (audioBlob) {
      setAudioUrl(URL.createObjectURL(audioBlob));
    } else {
      setAudioUrl(null);
    }
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioBlob]);

  // ML Processing simulation
  const processScreening = () => {
    setCallStatus('processing');
    setStageIdx(3);
    setProcessingStage('upload');
    setTimeout(() => setProcessingStage('extract'), 1000);
    setTimeout(() => setProcessingStage('audio_ml'), 2000);
    setTimeout(() => setProcessingStage('symptom_ml'), 3000);
    setTimeout(() => setProcessingStage('combine'), 4000);
    setTimeout(() => {
      setProcessingStage('done');
      setCallStatus('completed');
      setStageIdx(4);
      setScreeningResult({
        screening_id: 'sim_' + Date.now(),
        phone: '+91' + Math.floor(1000000000 + Math.random() * 9000000000),
        audio_risk: randomRisk(),
        symptom_risk: randomRisk(),
        combined_risk: randomRisk(),
        confidence: randomConfidence(),
        timestamp: new Date().toISOString(),
      });
    }, 5000);
  };

  // Send result to dashboard
  const sendResult = () => {
    if (!screeningResult) return;
    window.dispatchEvent(
      new CustomEvent('new_screening', { detail: screeningResult })
    );
    // Optionally show toast or confirmation
  };

  // Waveform simulation
  const renderWaveform = () => {
    if (!isRecording) return null;
    return (
      <div className="flex gap-1 mt-2">
        {[...Array(32)].map((_, i) => (
          <div key={i} className="bg-blue-400 rounded" style={{ height: Math.random() * 24 + 8, width: 4 }} />
        ))}
      </div>
    );
  };

  // Progress animation for ML
  const renderProcessingStage = () => {
    if (!processingStage) return null;
    const stages = [
      { key: 'upload', label: 'Uploading audio...' },
      { key: 'extract', label: 'Extracting MFCC features...' },
      { key: 'audio_ml', label: 'Running audio ML model...' },
      { key: 'symptom_ml', label: 'Running symptom ML model...' },
      { key: 'combine', label: 'Combining risk score...' },
      { key: 'done', label: 'Completed.' },
    ];
    return (
      <div className="mt-4">
        {stages.map((s, idx) => (
          <motion.div
            key={s.key}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: processingStage === s.key ? 1 : 0.5, x: 0 }}
            transition={{ duration: 0.3 }}
            className={`mb-2 text-sm ${processingStage === s.key ? 'font-bold text-blue-700' : 'text-gray-500'}`}
          >
            {s.label}
          </motion.div>
        ))}
      </div>
    );
  };

  // IVR Call Flow Visualization
  const renderCallFlow = () => (
    <div className="grid grid-cols-5 gap-4 mt-4">
      {CALL_STAGES.map((stage, idx) => (
        <motion.div
          key={stage.key}
          initial={{ scale: 0.9 }}
          animate={{ scale: stageIdx === idx ? 1.1 : 1 }}
          transition={{ duration: 0.2 }}
          className={`flex flex-col items-center p-3 rounded-xl shadow-md ${stageIdx === idx ? 'bg-blue-100 border-blue-500 border' : 'bg-white'}`}
        >
          <div className="mb-2 text-2xl">{stage.icon}</div>
          <div className={`text-xs ${stageIdx === idx ? 'font-bold text-blue-700' : 'text-gray-500'}`}>{stage.label}</div>
        </motion.div>
      ))}
    </div>
  );

  // Call Status Panel
  const renderCallStatusPanel = () => {
    const status = CALL_STATUS_MAP[callStatus] || CALL_STATUS_MAP['disconnected'];
    return (
      <div className="flex items-center gap-3 mb-4">
        <span className="text-xl">{status.icon}</span>
        <span className={`font-bold text-${status.color}-700`}>{status.label}</span>
      </div>
    );
  };

  // Audio preview controls
  const [audioPlaying, setAudioPlaying] = useState(false);
  const audioRef = useRef(null);
  const playAudio = () => {
    if (audioRef.current) {
      audioRef.current.play();
      setAudioPlaying(true);
    }
  };
  const pauseAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      setAudioPlaying(false);
    }
  };
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.onended = () => setAudioPlaying(false);
    }
  }, [audioUrl]);

  // Navigation button
  const renderNavButton = () => (
    <button
      className="mt-6 px-4 py-2 bg-gray-200 rounded-xl shadow hover:bg-gray-300 flex items-center gap-2"
      onClick={goBack}
    >
      <ArrowLeft /> Back to Dashboard
    </button>
  );

  return (
    <div className="max-w-3xl mx-auto p-6 grid gap-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold">BharatVani IVR Call Simulation</h2>
        {renderNavButton()}
      </div>

      {/* Call Status Panel */}
      <div className="rounded-xl shadow-md p-6 bg-white">
        {renderCallStatusPanel()}
        <div className="flex gap-2 mt-2">
          <button className="px-3 py-2 bg-blue-500 text-white rounded shadow" onClick={connectCall} disabled={callStatus === 'connected' || callStatus === 'recording' || callStatus === 'processing'}>Connect Call</button>
          <button className="px-3 py-2 bg-red-500 text-white rounded shadow" onClick={disconnectCall} disabled={callStatus === 'disconnected'}>Disconnect Call</button>
        </div>
      </div>

      {/* IVR Call Flow Visualization */}
      <div className="rounded-xl shadow-md p-6 bg-white">
        <h3 className="font-semibold mb-2">IVR Call Flow</h3>
        {renderCallFlow()}
      </div>

      {/* Microphone Recording */}
      <div className="rounded-xl shadow-md p-6 bg-white">
        <h3 className="font-semibold mb-2">Microphone Recording</h3>
        <div className="flex gap-2 mb-2">
          <button className="px-3 py-2 bg-green-500 text-white rounded shadow" onClick={startRecording} disabled={callStatus !== 'connected' || isRecording}>Start Recording</button>
          <button className="px-3 py-2 bg-yellow-500 text-white rounded shadow" onClick={stopRecording} disabled={!isRecording}>Stop Recording</button>
        </div>
        {isRecording && <div className="text-blue-700 font-bold">Recording... {recordingTime}s</div>}
        {renderWaveform()}
      </div>

      {/* Audio Preview */}
      {audioBlob && (
        <div className="rounded-xl shadow-md p-6 bg-white">
          <h3 className="font-semibold mb-2">Audio Preview</h3>
          <div className="flex items-center gap-2 mb-2">
            <button className="px-3 py-2 bg-blue-400 text-white rounded shadow" onClick={playAudio} disabled={audioPlaying}><Play /></button>
            <button className="px-3 py-2 bg-gray-400 text-white rounded shadow" onClick={pauseAudio} disabled={!audioPlaying}><Pause /></button>
            <button className="px-3 py-2 bg-red-400 text-white rounded shadow" onClick={deleteRecording}><Trash /></button>
          </div>
          <audio ref={audioRef} src={audioUrl} controls style={{ display: 'none' }} />
        </div>
      )}

      {/* ML Processing Simulation */}
      <div className="rounded-xl shadow-md p-6 bg-white">
        <h3 className="font-semibold mb-2">ML Processing Simulation</h3>
        <button className="px-3 py-2 bg-purple-500 text-white rounded shadow" onClick={processScreening} disabled={!audioBlob || callStatus !== 'connected'}>Process Screening</button>
        {renderProcessingStage()}
        {screeningResult && (
          <div className="mt-4 p-4 rounded bg-blue-50">
            <div className="font-bold text-lg mb-2">AI Risk Result</div>
            <div className="grid grid-cols-2 gap-2">
              <div><span className="font-semibold">Audio Risk:</span> {screeningResult.audio_risk}</div>
              <div><span className="font-semibold">Symptom Risk:</span> {screeningResult.symptom_risk}</div>
              <div><span className="font-semibold">Combined Risk:</span> {screeningResult.combined_risk}</div>
              <div><span className="font-semibold">Confidence:</span> {screeningResult.confidence}</div>
            </div>
            <button className="mt-4 px-4 py-2 bg-green-600 text-white rounded shadow" onClick={sendResult}>Send Result</button>
          </div>
        )}
      </div>
    </div>
  );
}
