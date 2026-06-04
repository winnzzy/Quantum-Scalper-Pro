import React, { useState } from 'react';
import { useAuthStore } from '../store/authStore';
import { toast } from 'react-hot-toast';
import { User, Bell, Lock, Globe, Save } from 'lucide-react';

const Settings: React.FC = () => {
  const { user } = useAuthStore();
  const [activeTab, setActiveTab] = useState('profile');
  const [formData, setFormData] = useState({
    first_name: user?.first_name || '',
    last_name: user?.last_name || '',
    timezone: user?.timezone || 'UTC',
    notifications: true,
    telegram_notifications: false,
    email_notifications: true,
  });

  const tabs = [
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'notifications', label: 'Notifications', icon: Bell },
    { id: 'security', label: 'Security', icon: Lock },
    { id: 'preferences', label: 'Preferences', icon: Globe },
  ];

  const handleSave = () => {
    toast.success('Settings saved successfully');
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Settings</h1>

      <div className="flex space-x-1 bg-gray-100 p-1 rounded-lg w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-white text-primary-700 shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <tab.icon className="w-4 h-4 mr-2" />
            {tab.label}
          </button>
        ))}
      </div>

      <div className="card">
        {activeTab === 'profile' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold">Profile Information</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">First Name</label>
                <input
                  type="text"
                  value={formData.first_name}
                  onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                  className="input"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Last Name</label>
                <input
                  type="text"
                  value={formData.last_name}
                  onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
                  className="input"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                <input
                  type="email"
                  value={user?.email || ''}
                  disabled
                  className="input bg-gray-50"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Timezone</label>
                <select
                  value={formData.timezone}
                  onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                  className="input"
                >
                  <option>UTC</option>
                  <option>America/New_York</option>
                  <option>Europe/London</option>
                  <option>Asia/Tokyo</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'notifications' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold">Notification Preferences</h3>
            <div className="space-y-3">
              {[
                { label: 'Trade Open/Close', key: 'notifications', desc: 'Get notified when trades are executed' },
                { label: 'Telegram Notifications', key: 'telegram_notifications', desc: 'Receive alerts via Telegram' },
                { label: 'Email Notifications', key: 'email_notifications', desc: 'Receive alerts via email' },
              ].map((item) => (
                <div key={item.key} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                  <div>
                    <p className="font-medium">{item.label}</p>
                    <p className="text-sm text-gray-500">{item.desc}</p>
                  </div>
                  <button
                    onClick={() => setFormData({ ...formData, [item.key]: !formData[item.key as keyof typeof formData] })}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      formData[item.key as keyof typeof formData] ? 'bg-primary-600' : 'bg-gray-300'
                    }`}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full shadow-md transform transition-transform ${
                      formData[item.key as keyof typeof formData] ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'security' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold">Security Settings</h3>
            <div className="space-y-4">
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="font-medium">Change Password</p>
                <p className="text-sm text-gray-500 mb-3">Update your account password</p>
                <button className="px-4 py-2 bg-primary-600 text-white rounded-lg text-sm hover:bg-primary-700">
                  Change Password
                </button>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="font-medium">Two-Factor Authentication</p>
                <p className="text-sm text-gray-500 mb-3">Add an extra layer of security</p>
                <button className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg text-sm hover:bg-gray-300">
                  Enable 2FA
                </button>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="font-medium">API Keys</p>
                <p className="text-sm text-gray-500 mb-3">Manage your API access keys</p>
                <button className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg text-sm hover:bg-gray-300">
                  Manage API Keys
                </button>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'preferences' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold">Trading Preferences</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Default Broker</label>
                <select className="input">
                  <option>Paper Trading</option>
                  <option>Binance Testnet</option>
                  <option>Binance Futures</option>
                  <option>MetaTrader 5</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Default Strategy</label>
                <select className="input">
                  <option>EMA Scalper</option>
                  <option>VWAP Scalper</option>
                  <option>Breakout Scalper</option>
                  <option>Mean Reversion</option>
                </select>
              </div>
            </div>
          </div>
        )}

        <div className="mt-6 pt-6 border-t border-gray-200">
          <button
            onClick={handleSave}
            className="flex items-center px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          >
            <Save className="w-4 h-4 mr-2" />
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
};

export default Settings;
