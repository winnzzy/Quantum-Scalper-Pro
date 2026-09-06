import React, { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from 'react-query';
import { Toaster } from 'react-hot-toast';
import Layout from './components/Layout';
import { useAuthStore } from './store/authStore';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const Trading = lazy(() => import('./pages/Trading'));
const Positions = lazy(() => import('./pages/Positions'));
const Analytics = lazy(() => import('./pages/Analytics'));
const Strategies = lazy(() => import('./pages/Strategies'));
const RiskCenter = lazy(() => import('./pages/RiskCenter'));
const Settings = lazy(() => import('./pages/Settings'));
const AdminDashboard = lazy(() => import('./pages/AdminDashboard'));
const Billing = lazy(() => import('./pages/Billing'));
const Validation = lazy(() => import('./pages/Validation'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function App() {
  const { isAuthenticated } = useAuthStore();

  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <Suspense fallback={<div className="min-h-screen bg-gray-950" />}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/" element={isAuthenticated ? <Layout /> : <Login />}>
              <Route index element={<Dashboard />} />
              <Route path="trading" element={<Trading />} />
              <Route path="positions" element={<Positions />} />
              <Route path="analytics" element={<Analytics />} />
              <Route path="strategies" element={<Strategies />} />
              <Route path="validation" element={<Validation />} />
              <Route path="risk" element={<RiskCenter />} />
              <Route path="settings" element={<Settings />} />
              <Route path="billing" element={<Billing />} />
              <Route path="admin" element={<AdminDashboard />} />
            </Route>
          </Routes>
        </Suspense>
      </Router>
      <Toaster position="top-right" />
    </QueryClientProvider>
  );
}

export default App;
