import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Suspense, lazy } from 'react';
import { MainLayout } from './components/layout/MainLayout';
import { ProtectedRoute } from './components/auth/ProtectedRoute';

// Lazy load all pages for code splitting
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Oxrana = lazy(() => import('./pages/Oxrana'));
const Sites = lazy(() => import('./pages/Sites'));
const Cameras = lazy(() => import('./pages/Cameras'));
const CameraDetail = lazy(() => import('./pages/CameraDetail'));
const CameraBindings = lazy(() => import('./pages/CameraBindings'));
const Rules = lazy(() => import('./pages/Rules'));
const Detectors = lazy(() => import('./pages/Detectors'));
const Actuators = lazy(() => import('./pages/Actuators'));
const Alarms = lazy(() => import('./pages/Alarms'));
const Notifiers = lazy(() => import('./pages/Notifiers'));
const System = lazy(() => import('./pages/System'));
const Login = lazy(() => import('./pages/Login'));

// Fallback component while lazy loading
const PageLoading = () => (
  <div className="flex items-center justify-center h-64">
    <div className="animate-spin rounded-full h-12 w-12 border-4 border-primary border-t-transparent" />
  </div>
);

function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoading />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/oxrana" element={<Oxrana />} />
            <Route path="/sites" element={<Sites />} />
            <Route path="/cameras" element={<Cameras />} />
            <Route path="/sites/:siteId/cameras" element={<Cameras />} />
            <Route path="/sites/:siteId/cameras/:cameraId/bindings" element={<CameraBindings />} />
            <Route path="/sites/:siteId/cameras/:cameraId" element={<CameraDetail />} />
            <Route path="/sites/:siteId/rules" element={<Rules />} />
            <Route path="/sites/:siteId/notifiers" element={<Notifiers />} />
            <Route path="/sites/:siteId/detectors" element={<Detectors />} />
            <Route path="/sites/:siteId/actuators" element={<Actuators />} />
            <Route path="/sites/:siteId/alarms" element={<Alarms />} />
            <Route path="/detectors" element={<Detectors />} />
            <Route path="/actuators" element={<Actuators />} />
            <Route path="/alarms" element={<Alarms />} />
            <Route path="/notifiers" element={<Notifiers />} />
            <Route path="/system" element={<System />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;