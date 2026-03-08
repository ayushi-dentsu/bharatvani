import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Dashboard from './components/Dashboard';
import IVRSimulation from './pages/IVRSimulation';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/admin-dashboard" element={<Dashboard />} />
        <Route path="/ivr-simulation" element={<IVRSimulation />} />
        <Route path="/" element={<Navigate to="/admin-dashboard" />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
