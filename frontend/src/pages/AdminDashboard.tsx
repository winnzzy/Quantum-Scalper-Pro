import React from 'react';
import { useQuery } from 'react-query';
import { Users, TrendingUp, Shield, Activity } from 'lucide-react';

const AdminDashboard: React.FC = () => {
  // Mock data for admin dashboard
  const stats = [
    { title: 'Total Users', value: '1,234', change: '+12%', icon: Users, color: 'bg-blue-500' },
    { title: 'Active Traders', value: '856', change: '+8%', icon: Activity, color: 'bg-green-500' },
    { title: 'Total Trades', value: '45.2K', change: '+23%', icon: TrendingUp, color: 'bg-purple-500' },
    { title: 'System Health', value: '99.9%', change: '+0.1%', icon: Shield, color: 'bg-primary-500' },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Admin Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat) => (
          <div key={stat.title} className="card">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">{stat.title}</p>
                <p className="text-2xl font-bold mt-1">{stat.value}</p>
                <p className="text-sm text-success mt-1">{stat.change}</p>
              </div>
              <div className={`p-3 rounded-lg ${stat.color}`}>
                <stat.icon className="w-6 h-6 text-white" />
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-lg font-semibold mb-4">User Management</h3>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">User</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Plan</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Status</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Trades</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { user: 'john@example.com', plan: 'Pro', status: 'Active', trades: 156 },
                  { user: 'jane@example.com', plan: 'Basic', status: 'Active', trades: 89 },
                  { user: 'bob@example.com', plan: 'Enterprise', status: 'Active', trades: 342 },
                ].map((row, i) => (
                  <tr key={i} className="border-b border-gray-100">
                    <td className="py-3 px-4">{row.user}</td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-1 bg-primary-100 text-primary-700 text-xs rounded-full">
                        {row.plan}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full">
                        {row.status}
                      </span>
                    </td>
                    <td className="py-3 px-4">{row.trades}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold mb-4">System Status</h3>
          <div className="space-y-3">
            {[
              { service: 'Trading Engine', status: 'Operational', uptime: '99.9%' },
              { service: 'Database', status: 'Operational', uptime: '99.99%' },
              { service: 'Redis Cache', status: 'Operational', uptime: '100%' },
              { service: 'Broker Connection', status: 'Operational', uptime: '99.5%' },
              { service: 'AI Filter', status: 'Operational', uptime: '99.8%' },
            ].map((service) => (
              <div key={service.service} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <p className="font-medium text-sm">{service.service}</p>
                  <p className="text-xs text-gray-500">Uptime: {service.uptime}</p>
                </div>
                <span className="px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full">
                  {service.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdminDashboard;
