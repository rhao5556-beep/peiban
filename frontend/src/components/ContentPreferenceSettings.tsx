/**
 * 内容推荐偏好设置组件
 * 
 * 功能：
 * 1. 启用/禁用推荐开关
 * 2. 每日推荐数量设置
 * 3. 来源选择器
 * 4. 免打扰时间设置
 */
import React, { useState, useEffect } from 'react';
import { api } from '../services/api';

interface ContentPreference {
  enabled: boolean;
  daily_limit: number;
  preferred_sources: string[];
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
}

const AVAILABLE_SOURCES = [
  { id: 'rss', name: 'RSS 订阅' },
  { id: 'weibo', name: '微博热搜' },
  { id: 'zhihu', name: '知乎热榜' },
  { id: 'bilibili', name: 'B站热门' }
];

export const ContentPreferenceSettings: React.FC = () => {
  const [preference, setPreference] = useState<ContentPreference>({
    enabled: false,
    daily_limit: 1,
    preferred_sources: [],
    quiet_hours_start: null,
    quiet_hours_end: null
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    fetchPreference();
  }, []);

  const fetchPreference = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const data = await api.getContentPreference();
      setPreference(data);
    } catch (err: any) {
      console.error('Failed to fetch preference:', err);
      setError(err.message || '获取偏好设置失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    
    try {
      await api.updateContentPreference(preference);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err: any) {
      console.error('Failed to save preference:', err);
      setError(err.message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const toggleSource = (sourceId: string) => {
    setPreference(prev => ({
      ...prev,
      preferred_sources: prev.preferred_sources.includes(sourceId)
        ? prev.preferred_sources.filter(s => s !== sourceId)
        : [...prev.preferred_sources, sourceId]
    }));
  };

  if (loading) {
    return (
      <div className="content-preference-settings">
        <h2 className="text-xl font-semibold mb-4">推荐设置</h2>
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
          <span className="ml-3 text-gray-600">加载中...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="content-preference-settings">
      <h2 className="text-xl font-semibold mb-4">推荐设置</h2>
      
      <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-6">
        
        {/* 启用开关 */}
        <div className="flex items-center justify-between p-4 bg-blue-50 border-2 border-blue-200 rounded-lg">
          <div>
            <h3 className="font-medium text-gray-900">启用内容推荐</h3>
            <p className="text-sm text-gray-600 mt-1">
              {preference.enabled 
                ? '✓ 已启用 - 可以配置下方设置' 
                : '⚠️ 请先打开此开关，然后才能配置其他设置'}
            </p>
          </div>
          <button
            onClick={() => setPreference(prev => ({ ...prev, enabled: !prev.enabled }))}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              preference.enabled ? 'bg-blue-600' : 'bg-gray-200'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                preference.enabled ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>
        
        {/* 禁用提示 */}
        {!preference.enabled && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <p className="text-yellow-800 text-sm">
              👆 请先点击上方的"启用内容推荐"开关，将其打开（变成蓝色），然后下方的所有设置就可以修改了。
            </p>
          </div>
        )}

        {/* 每日限额 */}
        <div className={!preference.enabled ? 'opacity-50' : ''}>
          <label className="block font-medium text-gray-900 mb-2">
            每日推荐数量 {!preference.enabled && <span className="text-xs text-gray-400">(需先启用推荐)</span>}
          </label>
          <select
            value={preference.daily_limit}
            onChange={(e) => setPreference(prev => ({ ...prev, daily_limit: parseInt(e.target.value) }))}
            disabled={!preference.enabled}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:text-gray-500 disabled:cursor-not-allowed"
          >
            <option value={1}>1 条</option>
            <option value={2}>2 条</option>
            <option value={3}>3 条</option>
            <option value={5}>5 条</option>
          </select>
          <p className="text-sm text-gray-500 mt-1">
            每天最多推荐的内容数量
          </p>
        </div>

        {/* 来源选择 */}
        <div className={!preference.enabled ? 'opacity-50' : ''}>
          <label className="block font-medium text-gray-900 mb-2">
            内容来源 {!preference.enabled && <span className="text-xs text-gray-400">(需先启用推荐)</span>}
          </label>
          <div className="space-y-2">
            {AVAILABLE_SOURCES.map(source => (
              <label
                key={source.id}
                className={`flex items-center space-x-3 ${preference.enabled ? 'cursor-pointer' : 'cursor-not-allowed'}`}
              >
                <input
                  type="checkbox"
                  checked={preference.preferred_sources.includes(source.id)}
                  onChange={() => toggleSource(source.id)}
                  disabled={!preference.enabled}
                  className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                />
                <span className={preference.enabled ? 'text-gray-900' : 'text-gray-500'}>
                  {source.name}
                </span>
              </label>
            ))}
          </div>
          <p className="text-sm text-gray-500 mt-2">
            留空则从所有来源推荐
          </p>
        </div>

        {/* 免打扰时间 */}
        <div className={!preference.enabled ? 'opacity-50' : ''}>
          <label className="block font-medium text-gray-900 mb-2">
            免打扰时间 {!preference.enabled && <span className="text-xs text-gray-400">(需先启用推荐)</span>}
          </label>
          <div className="flex items-center space-x-3">
            <input
              type="time"
              value={preference.quiet_hours_start || ''}
              onChange={(e) => setPreference(prev => ({ ...prev, quiet_hours_start: e.target.value || null }))}
              disabled={!preference.enabled}
              className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:text-gray-500 disabled:cursor-not-allowed"
            />
            <span className="text-gray-500">至</span>
            <input
              type="time"
              value={preference.quiet_hours_end || ''}
              onChange={(e) => setPreference(prev => ({ ...prev, quiet_hours_end: e.target.value || null }))}
              disabled={!preference.enabled}
              className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:text-gray-500 disabled:cursor-not-allowed"
            />
          </div>
          <p className="text-sm text-gray-500 mt-1">
            在此时间段内不会收到推荐通知
          </p>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
            <p className="text-red-600 text-sm">{error}</p>
          </div>
        )}

        {/* 成功提示 */}
        {success && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-3">
            <p className="text-green-600 text-sm">✓ 保存成功</p>
          </div>
        )}

        {/* 保存按钮 */}
        <div className="flex justify-end pt-4 border-t border-gray-200">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {saving ? '保存中...' : '保存设置'}
          </button>
        </div>
      </div>

      {/* 说明信息 */}
      <div className="mt-4 bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h4 className="font-medium text-blue-900 mb-2">💡 温馨提示</h4>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• 推荐内容基于您的兴趣和对话历史</li>
          <li>• 只有好感度达到"朋友"及以上才会收到推荐</li>
          <li>• 您的反馈会帮助我们改进推荐质量</li>
        </ul>
      </div>
    </div>
  );
};
