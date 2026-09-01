import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from 'react-query';
import { Toaster } from 'react-hot-toast';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import Register from './pages/Register';
import Trading from './pages/Trading';
import Positions from './pages/Positions';
import Analytics from './pages/Analytics';
import Strategies from './pages/Strategies';
import RiskCenter from './pages/RiskCenter';
import Settings from './pages/Settings';
import AdminDashboard from './pages/AdminDashboard';
import Billing from './pages/Billing';
import { useAuthStore } from './store/authStore';

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
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/" element={isAuthenticated ? <Layout /> : <Login />}>
            <Route index element={<Dashboard />} />
            <Route path="trading" element={<Trading />} />
            <Route path="positions" element={<Positions />} />
            <Route path="analytics" element={<Analytics />} />
            <Route path="strategies" element={<Strategies />} />
            <Route path="risk" element={<RiskCenter />} />
            <Route path="settings" element={<Settings />} />
            <Route path="billing" element={<Billing />} />
            <Route path="admin" element={<AdminDashboard />} />
          </Route>
        </Routes>
      </Router>
      <Toaster position="top-right" />
    </QueryClientProvider>
  );
}

export default App;
