import type { GraphData, AffinityPoint, StreamEvent, MemoryStatusResponse, ProactiveMessage, ProactivePreferences } from '../types';
import { MOCK_GRAPH_DATA_DAY_1, MOCK_GRAPH_DATA_DAY_15, MOCK_GRAPH_DATA_DAY_30, MOCK_AFFINITY_HISTORY } from '../constants';

// ============================================================================
// ⚠️ BACKEND INTEGRATION CONFIG (READY FOR PRODUCTION)
// ============================================================================

// 1. 关闭 Mock，连接真实后端
const USE_MOCK_DATA = false; 

// 2. 更新为后端 v1 接口地址
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'; 

// 3. 动态获取 Token
let cachedToken: string | null = null;
let cachedUserId: string | null = null;

// 从 localStorage 恢复 user_id
const STORAGE_KEY = 'affinity_user_id';
const storedUserId = localStorage.getItem(STORAGE_KEY);
if (storedUserId) {
  cachedUserId = storedUserId;
}

const getToken = async (): Promise<string> => {
  if (cachedToken) return cachedToken;
  
  try {
    // 只有当 cachedUserId 有值时才发送 user_id
    const body = cachedUserId ? { user_id: cachedUserId } : {};
    const response = await fetch(`${API_BASE_URL}/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (response.ok) {
      const data = await response.json();
      const token = typeof data?.access_token === 'string' ? data.access_token : '';
      cachedToken = token;
      // 保存 user_id 到 localStorage
      if (data.user_id && !cachedUserId) {
        cachedUserId = data.user_id;
        localStorage.setItem(STORAGE_KEY, data.user_id);
      }
      return token;
    }
  } catch (e) {
    console.error('Failed to get token', e);
  }
  return '';
};

// ============================================================================

const fetchJsonWithAuth = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const token = await getToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.headers || {}),
      'Authorization': `Bearer ${token}`
    }
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return response.json() as Promise<T>;
};

// Helper to mimic backend data transformation
const adaptBackendGraph = (backendData: any): GraphData => {
  if (!backendData || !backendData.nodes) return { nodes: [], edges: [] };
  
  // 关系类型中文映射
  const relationLabels: Record<string, string> = {
    'knows': '认识',
    'likes': '喜欢',
    'dislikes': '讨厌',
    'visited': '去过',
    'related': '相关'
  };
  
  return {
    nodes: backendData.nodes.map((n: any) => ({
      id: n.id,
      label: n.name || n.label, 
      type: n.type,
      weight: n.mention_count || n.weight || 10
    })),
    edges: backendData.edges.map((e: any) => {
      const weight = e.current_weight || e.weight || 1;
      const weightPercent = Math.round(weight * 100);
      const relationLabel = relationLabels[e.relation_type] || e.relation_type || 'related';
      return {
        id: e.id,
        source: e.source_id || e.source,
        target: e.target_id || e.target,
        label: `${relationLabel} (${weightPercent}%)`,  // 显示关系类型和权重百分比
        weight: weight
      };
    })
  };
};

export const api = {
  /**
   * 6.1.2 Fetch Graph Data
   * Endpoint: /api/v1/graph/?day=X (Note the trailing slash)
   */
  getGraphData: async (day: number): Promise<GraphData> => {
    if (USE_MOCK_DATA) {
      await new Promise(resolve => setTimeout(resolve, 500));
      if (day <= 1) return MOCK_GRAPH_DATA_DAY_1;
      if (day <= 15) return MOCK_GRAPH_DATA_DAY_15;
      return MOCK_GRAPH_DATA_DAY_30;
    }

    try {
      const token = await getToken();
      // Added trailing slash to match specification: /graph/
      const response = await fetch(`${API_BASE_URL}/graph/?day=${day}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data = await response.json();
      return adaptBackendGraph(data);
    } catch (e) {
      console.error("Failed to fetch graph", e);
      return { nodes: [], edges: [] };
    }
  },

  /**
   * 6.2.4 Fetch Affinity History
   * Endpoint: /api/v1/affinity/history
   */
  getAffinityHistory: async (): Promise<AffinityPoint[]> => {
    if (USE_MOCK_DATA) {
      return MOCK_AFFINITY_HISTORY;
    }
    try {
        const token = await getToken();
        const response = await fetch(`${API_BASE_URL}/affinity/history`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        
        // 转换后端格式到前端格式
        // 后端: { old_score, new_score, delta, trigger_event, signals, created_at }
        // 前端: { timestamp, value, event }
        return data.map((item: any, index: number) => ({
          timestamp: `第${index + 1}天`,
          value: Math.round((item.new_score || 0.5) * 100), // 转换 [-1,1] 到 [0,100]
          event: item.trigger_event === 'conversation' ? '' : item.trigger_event
        })).reverse(); // 按时间正序
    } catch (e) {
        console.error("Failed to fetch affinity", e);
        return [];
    }
  },

  getContentPreference: async (): Promise<{
    enabled: boolean;
    daily_limit: number;
    preferred_sources: string[];
    quiet_hours_start: string | null;
    quiet_hours_end: string | null;
  }> => {
    const data = await fetchJsonWithAuth<{
      content_recommendation_enabled: boolean;
      preferred_sources: string[];
      excluded_topics: string[];
      max_daily_recommendations: number;
      quiet_hours_start: string;
      quiet_hours_end: string;
      last_recommendation_at: string | null;
    }>('/content/preference');

    return {
      enabled: data.content_recommendation_enabled,
      daily_limit: data.max_daily_recommendations,
      preferred_sources: data.preferred_sources || [],
      quiet_hours_start: data.quiet_hours_start ?? null,
      quiet_hours_end: data.quiet_hours_end ?? null
    };
  },

  updateContentPreference: async (preference: {
    enabled: boolean;
    daily_limit: number;
    preferred_sources: string[];
    quiet_hours_start: string | null;
    quiet_hours_end: string | null;
  }): Promise<{
    enabled: boolean;
    daily_limit: number;
    preferred_sources: string[];
    quiet_hours_start: string | null;
    quiet_hours_end: string | null;
  }> => {
    const data = await fetchJsonWithAuth<{
      content_recommendation_enabled: boolean;
      preferred_sources: string[];
      excluded_topics: string[];
      max_daily_recommendations: number;
      quiet_hours_start: string;
      quiet_hours_end: string;
      last_recommendation_at: string | null;
    }>('/content/preference', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content_recommendation_enabled: preference.enabled,
        preferred_sources: preference.preferred_sources,
        max_daily_recommendations: preference.daily_limit,
        quiet_hours_start: preference.quiet_hours_start,
        quiet_hours_end: preference.quiet_hours_end
      })
    });

    return {
      enabled: data.content_recommendation_enabled,
      daily_limit: data.max_daily_recommendations,
      preferred_sources: data.preferred_sources || [],
      quiet_hours_start: data.quiet_hours_start ?? null,
      quiet_hours_end: data.quiet_hours_end ?? null
    };
  },

  getContentRecommendations: async (): Promise<Array<{
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
  }>> => {
    const data = await fetchJsonWithAuth<Array<{
      id: string;
      content_id: string;
      title: string;
      summary: string | null;
      url: string;
      source: string;
      tags: string[];
      published_at: string | null;
      match_score: number;
      rank_position: number;
      recommended_at: string;
      clicked_at: string | null;
      feedback: string | null;
    }>>('/content/recommendations');

    return data.map((item) => ({
      id: item.id,
      contentId: item.content_id,
      title: item.title,
      summary: item.summary,
      url: item.url,
      source: item.source,
      tags: item.tags || [],
      publishedAt: item.published_at,
      matchScore: item.match_score,
      rankPosition: item.rank_position,
      recommendedAt: item.recommended_at,
      clickedAt: item.clicked_at,
      feedback: item.feedback
    }));
  },

  submitRecommendationFeedback: async (
    recommendationId: string,
    action: 'clicked' | 'liked' | 'disliked' | 'ignored'
  ): Promise<{ success: boolean; message: string }> => {
    return fetchJsonWithAuth<{ success: boolean; message: string }>(
      `/content/recommendations/${recommendationId}/feedback`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      }
    );
  },

  getMemePreferences: async (): Promise<{
    user_id: string;
    meme_enabled: boolean;
    created_at: string;
    updated_at: string;
  }> => {
    return fetchJsonWithAuth('/memes/preferences');
  },

  updateMemePreferences: async (payload: { meme_enabled: boolean }): Promise<{
    user_id: string;
    meme_enabled: boolean;
    created_at: string;
    updated_at: string;
  }> => {
    const qs = new URLSearchParams({ meme_enabled: String(payload.meme_enabled) }).toString();
    return fetchJsonWithAuth(`/memes/preferences?${qs}`, { method: 'PUT' });
  },

  getTrendingMemes: async (limit = 20): Promise<{
    memes: Array<{
      id: string;
      image_url: string | null;
      text_description: string;
      source_platform: string;
      category: string | null;
      trend_score: number;
      trend_level: string;
      usage_count: number;
    }>;
    total: number;
  }> => {
    const qs = new URLSearchParams({ limit: String(limit) }).toString();
    return fetchJsonWithAuth(`/memes/trending?${qs}`);
  },

  getMemeStats: async (): Promise<{
    total_memes: number;
    approved_memes: number;
    trending_memes: number;
    acceptance_rate: number;
    avg_trend_score: number;
  }> => {
    return fetchJsonWithAuth('/memes/stats');
  },

  submitMemeFeedback: async (
    usageId: string,
    reaction: 'liked' | 'ignored' | 'disliked'
  ): Promise<{ success: boolean; message: string }> => {
    return fetchJsonWithAuth('/memes/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usage_id: usageId, reaction })
    });
  },

  getMemories: async (limit = 50): Promise<Array<{
    id: string;
    content: string;
    valence: number | null;
    status: string;
    created_at: string;
    committed_at: string | null;
  }>> => {
    const qs = new URLSearchParams({ limit: String(limit) }).toString();
    return fetchJsonWithAuth(`/memories/?${qs}`);
  },

  getMemory: async (memoryId: string): Promise<{
    id: string;
    content: string;
    valence: number | null;
    status: string;
    created_at: string;
    committed_at: string | null;
  }> => {
    return fetchJsonWithAuth(`/memories/${memoryId}`);
  },

  deleteMemories: async (memoryIds: string[]): Promise<any> => {
    return fetchJsonWithAuth('/memories/', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ memory_ids: memoryIds, delete_all: false })
    });
  },

  deleteAllMemories: async (): Promise<any> => {
    return fetchJsonWithAuth('/memories/', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delete_all: true })
    });
  },

  getDashboard: async (): Promise<any> => {
    const [affinity, memories] = await Promise.all([
      fetchJsonWithAuth<any>('/affinity/'),
      fetchJsonWithAuth<any>('/memories/?limit=50')
    ]);

    const relationshipScoreRaw = typeof affinity?.score === 'number' ? affinity.score : 0.5;
    const score100 = typeof affinity?.score_100 === 'number' ? affinity.score_100 : Math.round(relationshipScoreRaw * 100);
    const state = typeof affinity?.state === 'string' ? affinity.state : 'acquaintance';

    return {
      relationship: {
        state,
        state_display: affinity?.state_v2 ?? state,
        score: score100,
        score_raw: relationshipScoreRaw,
        hearts: ''
      },
      days_known: 0,
      memories: { count: Array.isArray(memories) ? memories.length : 0, can_view_details: true },
      feedback: { likes: 0, dislikes: 0, saves: 0, favorites: 0 },
      health_reminder: affinity?.health_state ? { message: String(affinity.health_state) } : null
    };
  },

  getProactiveMessages: async (status?: string, limit = 10): Promise<{ messages: ProactiveMessage[]; total: number }> => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (status) params.set('status', status);
    return fetchJsonWithAuth(`/proactive/messages?${params.toString()}`);
  },

  acknowledgeProactiveMessage: async (
    messageId: string,
    action: 'read' | 'ignore' | 'disable'
  ): Promise<{ success: boolean; message_id: string; action: string; status: string }> => {
    const params = new URLSearchParams({ action }).toString();
    return fetchJsonWithAuth(`/proactive/messages/${messageId}/ack?${params}`, { method: 'POST' });
  },

  getProactivePreferences: async (): Promise<ProactivePreferences> => {
    return fetchJsonWithAuth('/proactive/preferences');
  },

  updateProactivePreferences: async (preferences: ProactivePreferences): Promise<any> => {
    const params = new URLSearchParams({
      proactive_enabled: String(preferences.proactive_enabled),
      morning_greeting_enabled: String(preferences.morning_greeting_enabled),
      evening_greeting_enabled: String(preferences.evening_greeting_enabled),
      silence_reminder_enabled: String(preferences.silence_reminder_enabled),
      quiet_hours_start: preferences.quiet_hours_start,
      quiet_hours_end: preferences.quiet_hours_end,
      max_messages_per_day: String(preferences.max_messages_per_day),
      preferred_morning_time: preferences.preferred_morning_time,
      preferred_evening_time: preferences.preferred_evening_time
    }).toString();

    return fetchJsonWithAuth(`/proactive/preferences?${params}`, { method: 'PUT' });
  },

  /**
   * 2.1 & 2.2 Streaming Message (Fast Path)
   * Endpoint: /api/v1/sse/message
   */
  sendMessageStream: async function* (text: string, sessionId?: string): AsyncGenerator<StreamEvent> {
    if (USE_MOCK_DATA) {
      // Mock Stream Generator
      yield { type: 'start', session_id: 'mock_session_123' };
      await new Promise(r => setTimeout(r, 300));
      
      const words = ["I", " ", "hear", " ", "you.", " "];
      for (const word of words) {
        yield { type: 'text', content: word };
        await new Promise(r => setTimeout(r, 100));
      }

      if (text.toLowerCase().includes('coffee') || text.toLowerCase().includes('like')) {
        yield { type: 'text', content: "I'll remember that." };
        yield { 
            type: 'memory_pending', 
            memory_id: `mem_${Date.now()}`, 
            metadata: { topic: 'preference' } 
        };
      } else {
        yield { type: 'text', content: "Tell me more." };
      }
      
      yield { type: 'done' };
      return;
    }

    // Real Backend Implementation
    const token = await getToken();
    const response = await fetch(`${API_BASE_URL}/sse/message`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(sessionId ? { message: text, session_id: sessionId } : { message: text })
    });

    if (!response.body) throw new Error("No response body");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const processedEvents = new Set<string>(); // 去重：防止重复处理相同事件

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      const chunk = decoder.decode(value, { stream: true });
      buffer += chunk;
      
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmedLine = line.trim();
        if (!trimmedLine) continue;
        
        // SSE 标准格式：data: {...}
        if (!trimmedLine.startsWith('data: ')) continue;
        const cleanLine = trimmedLine.slice(6);

        try {
            if (cleanLine === '[DONE]') break;
            
            // 去重检查：使用事件内容作为唯一标识
            const eventKey = cleanLine;
            if (processedEvents.has(eventKey)) {
              console.debug("Skipping duplicate event:", cleanLine.substring(0, 50));
              continue;
            }
            processedEvents.add(eventKey);
            
            const event: StreamEvent = JSON.parse(cleanLine);
            yield event;
        } catch (e) {
            console.warn("Stream parse error", e, line);
        }
      }
    }
  },

  /**
   * 4.3 Polling Memory Status (Slow Path / Fallback)
   * Endpoint: /api/v1/memories/{id}
   */
  pollMemoryStatus: (
    memoryId: string,
    handlers: {
      onCommitted: () => void;
      onDeleted?: () => void;
      onTimeout?: () => void;
      onError?: (error: unknown) => void;
    }
  ) => {
    if (USE_MOCK_DATA) {
      setTimeout(() => {
        handlers.onCommitted();
      }, 3000);
      return;
    }

    let delay = 3000;
    const maxDelay = 10000;
    const timeout = 60000; 
    const start = Date.now();

    const tick = async () => {
      if (Date.now() - start > timeout) {
        console.warn(`Polling timeout for memory ${memoryId}`);
        handlers.onTimeout?.();
        return;
      }

      try {
        const token = await getToken();
        const res = await fetch(`${API_BASE_URL}/memories/${memoryId}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (res.ok) {
            const data: MemoryStatusResponse = await res.json();
            if (data.status === 'committed') {
              handlers.onCommitted();
              return;
            } else if (data.status === 'deleted') {
                handlers.onDeleted?.();
                return; 
            }
        } else if (res.status === 404) {
            handlers.onDeleted?.();
            return;
        }
      } catch (e) {
        console.error("Polling error", e);
        handlers.onError?.(e);
      }

      setTimeout(tick, delay);
      delay = Math.min(maxDelay, delay * 1.5);
    };

    tick();
  }
};
