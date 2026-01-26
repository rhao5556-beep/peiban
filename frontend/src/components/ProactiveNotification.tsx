import React, { useEffect, useState } from 'react';
import { Bell, X, Settings } from 'lucide-react';
import { api } from '../services/api';
import type { ProactiveMessage } from '../types';

interface ProactiveNotificationProps {
  onOpenSettings: () => void;
}

const ProactiveNotification: React.FC<ProactiveNotificationProps> = ({ onOpenSettings }) => {
  const [messages, setMessages] = useState<ProactiveMessage[]>([]);
  const [isVisible, setIsVisible] = useState(false);

  // 轮询获取待处理的主动消息
  useEffect(() => {
    let cancelled = false;
    let consecutiveFailures = 0;

    const fetchMessages = async () => {
      try {
        if (document.hidden) return;
        const data = await api.getProactiveMessages('pending');
        if (cancelled) return;
        consecutiveFailures = 0;
        if (data.messages && data.messages.length > 0) {
          setMessages(data.messages);
          setIsVisible(true);
        }
      } catch (e) {
        if (cancelled) return;
        consecutiveFailures = Math.min(consecutiveFailures + 1, 3);
      }
    };

    const scheduleNext = (baseMs: number) => {
      const jitter = Math.floor(Math.random() * 250);
      const timeoutMs = baseMs + jitter;
      return window.setTimeout(async () => {
        await fetchMessages();
        const backoffMs = [30000, 30000, 45000, 60000][consecutiveFailures] ?? 60000;
        timerId = scheduleNext(backoffMs);
      }, timeoutMs);
    };

    const initialDelayMs = import.meta.env.DEV ? 12000 : 1500;
    const initialTimerId = window.setTimeout(() => {
      fetchMessages();
    }, initialDelayMs);

    let timerId = scheduleNext(30000);

    const onVisibilityChange = () => {
      if (!document.hidden) {
        fetchMessages();
      }
    };
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      cancelled = true;
      window.clearTimeout(initialTimerId);
      window.clearTimeout(timerId);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, []);

  const handleAcknowledge = async (messageId: string, action: 'read' | 'ignore' | 'disable') => {
    try {
      await api.acknowledgeProactiveMessage(messageId, action);
      
      setMessages(prev => {
        const next = prev.filter(m => m.id !== messageId);
        if (next.length === 0) setIsVisible(false);
        return next;
      });
      
      // 如果用户选择禁用，打开设置页面
      if (action === 'disable') {
        onOpenSettings();
      }
    } catch (e) {
    }
  };

  if (!isVisible || messages.length === 0) {
    return null;
  }

  const currentMessage = messages[0];

  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-sm animate-slide-up">
      <div className="bg-white rounded-lg shadow-2xl border border-blue-200 overflow-hidden">
        {/* 头部 */}
        <div className="bg-gradient-to-r from-blue-500 to-blue-600 px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-white">
            <Bell size={18} />
            <span className="font-medium text-sm">AI 主动消息</span>
          </div>
          <button
            onClick={() => handleAcknowledge(currentMessage.id, 'ignore')}
            className="text-white hover:bg-white/20 rounded p-1 transition-colors"
            title="忽略"
          >
            <X size={16} />
          </button>
        </div>

        {/* 内容 */}
        <div className="p-4">
          <p className="text-gray-800 text-sm leading-relaxed mb-4">
            {currentMessage.content}
          </p>

          {/* 操作按钮 */}
          <div className="flex gap-2">
            <button
              onClick={() => handleAcknowledge(currentMessage.id, 'read')}
              className="flex-1 bg-blue-500 hover:bg-blue-600 text-white text-sm py-2 px-3 rounded-lg transition-colors font-medium"
            >
              知道了
            </button>
            <button
              onClick={() => handleAcknowledge(currentMessage.id, 'ignore')}
              className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2 px-3 rounded-lg transition-colors"
            >
              忽略
            </button>
            <button
              onClick={() => handleAcknowledge(currentMessage.id, 'disable')}
              className="bg-gray-100 hover:bg-gray-200 text-gray-600 p-2 rounded-lg transition-colors"
              title="关闭主动消息"
            >
              <Settings size={16} />
            </button>
          </div>

          {/* 消息计数 */}
          {messages.length > 1 && (
            <div className="mt-3 text-center text-xs text-gray-500">
              还有 {messages.length - 1} 条消息
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProactiveNotification;
