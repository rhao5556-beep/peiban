/**
 * 内容推荐组件
 * 
 * 功能：
 * 1. 显示今日推荐内容（最多3条）
 * 2. 支持点击链接（新标签页打开）
 * 3. 支持喜欢/不喜欢反馈
 * 4. 加载状态显示
 */
import React, { useState, useEffect } from 'react';
import { api } from '../services/api';

interface Recommendation {
  id: string;
  contentId: string;
  title: string;
  summary: string | null;
  url: string;
  source: string;
  tags: string[];
  publishedAt: string | null;
  matchScore: number;
  rankPosition: number;
  recommendedAt: string;
  clickedAt: string | null;
  feedback: string | null;
}

export const ContentRecommendation: React.FC = () => {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isEnabled, setIsEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    
    try {
      // 同时获取推荐列表和用户偏好
      const [recsData, prefData] = await Promise.all([
        api.getContentRecommendations(),
        api.getContentPreference()
      ]);
      
      setRecommendations(recsData);
      setIsEnabled(prefData.enabled);
    } catch (err: any) {
      console.error('Failed to fetch data:', err);
      
      // 提供更友好的错误信息
      let errorMessage = '获取推荐失败';
      if (err.message?.includes('500')) {
        errorMessage = '服务暂时不可用，请稍后再试';
      } else if (err.message?.includes('Network')) {
        errorMessage = '网络连接失败，请检查网络';
      } else if (err.message) {
        errorMessage = err.message;
      }
      
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleClick = async (rec: Recommendation) => {
    try {
      // 先提交点击反馈
      await api.submitRecommendationFeedback(rec.id, 'clicked');
      
      // 更新本地状态
      setRecommendations(prev =>
        prev.map(r =>
          r.id === rec.id ? { ...r, clickedAt: new Date().toISOString() } : r
        )
      );
      
      // 在新标签页打开链接（安全方式）
      const link = document.createElement('a');
      link.href = rec.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.click();
    } catch (err) {
      console.error('Failed to track click:', err);
      // 即使埋点失败也打开链接
      window.open(rec.url, '_blank', 'noopener,noreferrer');
    }
  };

  const handleLike = async (rec: Recommendation) => {
    try {
      await api.submitRecommendationFeedback(rec.id, 'liked');
      
      // 更新本地状态
      setRecommendations(prev =>
        prev.map(r =>
          r.id === rec.id ? { ...r, feedback: 'liked' } : r
        )
      );
    } catch (err) {
      console.error('Failed to submit like:', err);
    }
  };

  const handleDislike = async (rec: Recommendation) => {
    try {
      await api.submitRecommendationFeedback(rec.id, 'disliked');
      
      // 从列表中移除
      setRecommendations(prev => prev.filter(r => r.id !== rec.id));
    } catch (err) {
      console.error('Failed to submit dislike:', err);
    }
  };

  if (loading) {
    return (
      <div className="content-recommendation">
        <h2 className="text-xl font-semibold mb-4">今日推荐</h2>
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
          <span className="ml-3 text-gray-600">加载中...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="content-recommendation">
        <h2 className="text-xl font-semibold mb-4">今日推荐</h2>
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-start">
            <svg className="w-5 h-5 text-red-500 mt-0.5 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <div className="flex-1">
              <p className="text-red-600 font-medium">{error}</p>
              <button
                onClick={fetchData}
                className="mt-2 text-sm text-red-600 hover:text-red-800 underline"
              >
                重试
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (recommendations.length === 0) {
    return (
      <div className="content-recommendation">
        <h2 className="text-xl font-semibold mb-4">今日推荐</h2>
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center">
          <p className="text-gray-500">暂无推荐内容</p>
          <p className="text-sm text-gray-400 mt-2">
            {isEnabled === false 
              ? '请在设置中启用内容推荐功能' 
              : '系统正在为您准备推荐内容，请稍后查看'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="content-recommendation">
      <h2 className="text-xl font-semibold mb-4">今日推荐</h2>
      
      <div className="space-y-4">
        {recommendations.map((rec) => (
          <div
            key={rec.id}
            className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
          >
            {/* 标题和来源 */}
            <div className="flex items-start justify-between mb-2">
              <h3
                className="text-lg font-medium text-blue-600 hover:text-blue-800 cursor-pointer flex-1"
                onClick={() => handleClick(rec)}
              >
                {rec.title}
              </h3>
              <span className="ml-2 px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded">
                {rec.source}
              </span>
            </div>

            {/* 摘要 */}
            {rec.summary && (
              <p className="text-gray-600 text-sm mb-3 line-clamp-2">
                {rec.summary}
              </p>
            )}

            {/* 标签 */}
            {rec.tags && rec.tags.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3">
                {rec.tags.slice(0, 3).map((tag, idx) => (
                  <span
                    key={idx}
                    className="px-2 py-1 bg-blue-50 text-blue-600 text-xs rounded"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}

            {/* 操作按钮 */}
            <div className="flex items-center justify-between pt-3 border-t border-gray-100">
              <div className="flex items-center space-x-4">
                {/* 喜欢按钮 */}
                <button
                  onClick={() => handleLike(rec)}
                  disabled={rec.feedback === 'liked'}
                  className={`flex items-center space-x-1 text-sm ${
                    rec.feedback === 'liked'
                      ? 'text-green-600'
                      : 'text-gray-500 hover:text-green-600'
                  } transition-colors`}
                >
                  <svg
                    className="w-5 h-5"
                    fill={rec.feedback === 'liked' ? 'currentColor' : 'none'}
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5"
                    />
                  </svg>
                  <span>喜欢</span>
                </button>

                {/* 不喜欢按钮 */}
                <button
                  onClick={() => handleDislike(rec)}
                  className="flex items-center space-x-1 text-sm text-gray-500 hover:text-red-600 transition-colors"
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018a2 2 0 01.485.06l3.76.94m-7 10v5a2 2 0 002 2h.096c.5 0 .905-.405.905-.904 0-.715.211-1.413.608-2.008L17 13V4m-7 10h2m5-10h2a2 2 0 012 2v6a2 2 0 01-2 2h-2.5"
                    />
                  </svg>
                  <span>不感兴趣</span>
                </button>
              </div>

              {/* 匹配分数 */}
              <div className="text-xs text-gray-400">
                匹配度: {(rec.matchScore * 100).toFixed(0)}%
              </div>
            </div>

            {/* 已点击标记 */}
            {rec.clickedAt && (
              <div className="mt-2 text-xs text-gray-400">
                ✓ 已查看
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
