import React, { useEffect, useState } from 'react';
import { Smile } from 'lucide-react';
import { api } from '../services/api';

export const MemePreferenceSettings: React.FC = () => {
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadPreferences();
  }, []);

  const loadPreferences = async () => {
    try {
      const data = await api.getMemePreferences();
      setEnabled(data.meme_enabled);
    } catch (e) {
      console.error('Failed to load meme preferences', e);
    }
  };

  const handleToggle = async (value: boolean) => {
    setLoading(true);
    try {
      await api.updateMemePreferences({ meme_enabled: value });
      setEnabled(value);
    } catch (e) {
      console.error('Failed to update meme preferences', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center gap-3 mb-4">
        <Smile className="text-yellow-500" size={24} />
        <h3 className="text-lg font-semibold text-gray-800">表情包设置</h3>
      </div>

      <label className="flex items-center justify-between cursor-pointer p-4 rounded-lg hover:bg-gray-50 transition-colors">
        <div>
          <div className="font-medium text-gray-800">启用表情包</div>
          <div className="text-sm text-gray-600">AI 会在对话中适时使用表情包</div>
        </div>
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => handleToggle(e.target.checked)}
          disabled={loading}
          className="w-5 h-5 text-yellow-500 rounded focus:ring-2 focus:ring-yellow-500 disabled:opacity-50"
        />
      </label>
    </div>
  );
};
