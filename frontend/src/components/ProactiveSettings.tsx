import React, { useEffect, useState } from 'react';
import { Bell, Clock, Moon, Sun, MessageCircle, X } from 'lucide-react';
import { api } from '../services/api';
import type { ProactivePreferences } from '../types';

interface ProactiveSettingsProps {
  isOpen: boolean;
  onClose: () => void;
}

const ProactiveSettings: React.FC<ProactiveSettingsProps> = ({ isOpen, onClose }) => {
  const [preferences, setPreferences] = useState<ProactivePreferences>({
    proactive_enabled: true,
    morning_greeting_enabled: true,
    evening_greeting_enabled: true,
    silence_reminder_enabled: true,
    quiet_hours_start: "22:00",
    quiet_hours_end: "08:00",
    max_messages_per_day: 3,
    preferred_morning_time: "08:00",
    preferred_evening_time: "22:00"
  });
  const [loading, setLoading] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  useEffect(() => {
    if (isOpen) {
      loadPreferences();
    }
  }, [isOpen]);

  const loadPreferences = async () => {
    try {
      const data = await api.getProactivePreferences();
      setPreferences(data);
    } catch (e) {
      console.error('Failed to load proactive preferences', e);
    }
  };

  const handleSave = async () => {
    setLoading(true);
    setSaveStatus('saving');
    
    try {
      await api.updateProactivePreferences(preferences);
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch (e) {
      console.error('Failed to save preferences', e);
      setSaveStatus('error');
      setTimeout(() => setSaveStatus('idle'), 2000);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* 头部 */}
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Bell className="text-blue-500" size={24} />
            <h2 className="text-xl font-bold text-gray-800">主动消息设置</h2>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <X size={24} />
          </button>
        </div>

        {/* 内容 */}
        <div className="p-6 space-y-6">
          {/* 总开关 */}
          <div className="bg-blue-50 rounded-lg p-4">
            <label className="flex items-center justify-between cursor-pointer">
              <div className="flex items-center gap-3">
                <Bell className="text-blue-500" size={20} />
                <div>
                  <div className="font-medium text-gray-800">启用主动消息</div>
                  <div className="text-sm text-gray-600">AI 会在合适的时候主动向你发送消息</div>
                </div>
              </div>
              <input
                type="checkbox"
                checked={preferences.proactive_enabled}
                onChange={(e) => setPreferences({ ...preferences, proactive_enabled: e.target.checked })}
                className="w-5 h-5 text-blue-500 rounded focus:ring-2 focus:ring-blue-500"
              />
            </label>
          </div>

          {/* 消息类型 */}
          <div className="space-y-4">
            <h3 className="font-semibold text-gray-800 flex items-center gap-2">
              <MessageCircle size={18} />
              消息类型
            </h3>

            <label className="flex items-center justify-between cursor-pointer p-3 rounded-lg hover:bg-gray-50 transition-colors">
              <div className="flex items-center gap-3">
                <Sun className="text-yellow-500" size={18} />
                <div>
                  <div className="font-medium text-gray-700">早安问候</div>
                  <div className="text-sm text-gray-500">每天早上 {preferences.preferred_morning_time}</div>
                </div>
              </div>
              <input
                type="checkbox"
                checked={preferences.morning_greeting_enabled}
                onChange={(e) => setPreferences({ ...preferences, morning_greeting_enabled: e.target.checked })}
                disabled={!preferences.proactive_enabled}
                className="w-4 h-4 text-blue-500 rounded focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              />
            </label>

            <label className="flex items-center justify-between cursor-pointer p-3 rounded-lg hover:bg-gray-50 transition-colors">
              <div className="flex items-center gap-3">
                <Moon className="text-indigo-500" size={18} />
                <div>
                  <div className="font-medium text-gray-700">晚安问候</div>
                  <div className="text-sm text-gray-500">每天晚上 {preferences.preferred_evening_time}</div>
                </div>
              </div>
              <input
                type="checkbox"
                checked={preferences.evening_greeting_enabled}
                onChange={(e) => setPreferences({ ...preferences, evening_greeting_enabled: e.target.checked })}
                disabled={!preferences.proactive_enabled}
                className="w-4 h-4 text-blue-500 rounded focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              />
            </label>

            <label className="flex items-center justify-between cursor-pointer p-3 rounded-lg hover:bg-gray-50 transition-colors">
              <div className="flex items-center gap-3">
                <Clock className="text-gray-500" size={18} />
                <div>
                  <div className="font-medium text-gray-700">沉默提醒</div>
                  <div className="text-sm text-gray-500">长时间未互动时的关心消息</div>
                </div>
              </div>
              <input
                type="checkbox"
                checked={preferences.silence_reminder_enabled}
                onChange={(e) => setPreferences({ ...preferences, silence_reminder_enabled: e.target.checked })}
                disabled={!preferences.proactive_enabled}
                className="w-4 h-4 text-blue-500 rounded focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              />
            </label>
          </div>

          {/* 频率控制 */}
          <div className="space-y-4">
            <h3 className="font-semibold text-gray-800">频率控制</h3>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                每日最大消息数
              </label>
              <input
                type="number"
                min="1"
                max="10"
                value={preferences.max_messages_per_day}
                onChange={(e) => setPreferences({ ...preferences, max_messages_per_day: parseInt(e.target.value) || 3 })}
                disabled={!preferences.proactive_enabled}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:bg-gray-100"
              />
            </div>
          </div>

          {/* 免打扰时段 */}
          <div className="space-y-4">
            <h3 className="font-semibold text-gray-800">免打扰时段</h3>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  开始时间
                </label>
                <input
                  type="time"
                  value={preferences.quiet_hours_start}
                  onChange={(e) => setPreferences({ ...preferences, quiet_hours_start: e.target.value })}
                  disabled={!preferences.proactive_enabled}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:bg-gray-100"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  结束时间
                </label>
                <input
                  type="time"
                  value={preferences.quiet_hours_end}
                  onChange={(e) => setPreferences({ ...preferences, quiet_hours_end: e.target.value })}
                  disabled={!preferences.proactive_enabled}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:bg-gray-100"
                />
              </div>
            </div>
          </div>
        </div>

        {/* 底部按钮 */}
        <div className="sticky bottom-0 bg-gray-50 border-t border-gray-200 px-6 py-4 flex items-center justify-between">
          <div className="text-sm text-gray-600">
            {saveStatus === 'saved' && <span className="text-green-600">✓ 保存成功</span>}
            {saveStatus === 'error' && <span className="text-red-600">✗ 保存失败</span>}
          </div>
          
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-700 hover:bg-gray-200 rounded-lg transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleSave}
              disabled={loading}
              className="px-6 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
            >
              {loading ? '保存中...' : '保存设置'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProactiveSettings;
