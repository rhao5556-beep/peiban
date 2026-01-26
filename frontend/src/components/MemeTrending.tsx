import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { Smile, RefreshCcw } from 'lucide-react';

type TrendingMeme = {
  id: string;
  image_url: string | null;
  text_description: string;
  source_platform: string;
  category: string | null;
  trend_score: number;
  trend_level: string;
  usage_count: number;
};

export const MemeTrending: React.FC = () => {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [memes, setMemes] = useState<TrendingMeme[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const pref = await api.getMemePreferences();
      setEnabled(pref.meme_enabled);
      if (!pref.meme_enabled) {
        setMemes([]);
        return;
      }
      const trending = await api.getTrendingMemes(10);
      setMemes(trending.memes || []);
    } catch (e: any) {
      setError(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <Smile className="text-yellow-500" size={24} />
          <h3 className="text-lg font-semibold text-gray-800">热门表情包</h3>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50"
        >
          <RefreshCcw size={16} />
          刷新
        </button>
      </div>

      {loading && (
        <div className="text-sm text-gray-500">加载中...</div>
      )}

      {!loading && error && (
        <div className="text-sm text-red-600">{error}</div>
      )}

      {!loading && enabled === false && (
        <div className="text-sm text-gray-500">你已关闭表情包功能，开启后这里会展示热门表情包。</div>
      )}

      {!loading && enabled !== false && !error && memes.length === 0 && (
        <div className="text-sm text-gray-500">暂无热门表情包。</div>
      )}

      {!loading && !error && enabled !== false && memes.length > 0 && (
        <div className="space-y-3">
          {memes.map((m) => (
            <div key={m.id} className="border border-gray-200 rounded-lg p-4">
              <div className="flex items-start gap-4">
                {m.image_url ? (
                  <img
                    src={m.image_url}
                    alt="meme"
                    className="w-20 h-20 object-cover rounded-lg border border-gray-100"
                  />
                ) : (
                  <div className="w-20 h-20 rounded-lg border border-gray-100 bg-gray-50 flex items-center justify-center text-xs text-gray-400">
                    无图片
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-gray-900 break-words">{m.text_description}</div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-500">
                    <span className="px-2 py-1 bg-gray-50 border border-gray-100 rounded">
                      {m.source_platform}
                    </span>
                    <span className="px-2 py-1 bg-gray-50 border border-gray-100 rounded">
                      {m.trend_level} · {Math.round(m.trend_score)}
                    </span>
                    {m.category && (
                      <span className="px-2 py-1 bg-gray-50 border border-gray-100 rounded">
                        {m.category}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

