import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import WowDashboard from './components/wow/WowDashboard';
import IVRSimulation from './pages/IVRSimulation';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/admin-dashboard" element={<WowDashboard />} />
        <Route path="/ivr-simulation" element={<IVRSimulation />} />
        <Route path="/" element={<Navigate to="/ivr-simulation" />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
