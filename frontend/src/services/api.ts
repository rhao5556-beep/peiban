import type { GraphData, AffinityPoint, StreamEvent, MemoryStatusResponse } from '../types';
import { MOCK_GRAPH_DATA_DAY_1, MOCK_GRAPH_DATA_DAY_15, MOCK_GRAPH_DATA_DAY_30, MOCK_AFFINITY_HISTORY } from '../constants';

// ============================================================================
// ⚠️ BACKEND INTEGRATION CONFIG (READY FOR PRODUCTION)
// ============================================================================

// 1. 关闭 Mock，连接真实后端
const USE_MOCK_DATA = false; 

// 2. 更新为后端 v1 接口地址
const normalizeBaseUrl = (value: string) => value.replace(/\/+$/, '');
const API_BASE_URL = normalizeBaseUrl((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api/v1'); 

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
      const token = (data?.access_token as string | undefined) ?? '';
      cachedToken = token || null;
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
      weight: n.mention_count || n.weight || 10,
      properties: n
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
        weight: weight,
        properties: e
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

  getDashboard: async () => {
    const token = await getToken();
    const res = await fetch(`${API_BASE_URL}/affinity/dashboard`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  getMemories: async (limit = 50) => {
    const token = await getToken();
    const res = await fetch(`${API_BASE_URL}/memories/?limit=${limit}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  getMemory: async (memoryId: string) => {
    const token = await getToken();
    const res = await fetch(`${API_BASE_URL}/memories/${memoryId}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  deleteMemories: async (ids: string[]) => {
    const token = await getToken();
    const res = await fetch(`${API_BASE_URL}/memories/`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ memory_ids: ids })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  deleteAllMemories: async () => {
    const token = await getToken();
    const res = await fetch(`${API_BASE_URL}/memories/`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ delete_all: true })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  getContentRecommendations: async () => {
    const token = await getToken();
    const res = await fetch(`${API_BASE_URL}/content/recommendations`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return (data || []).map((r: any) => ({
      id: r.id,
      contentId: r.content_id,
      title: r.title,
      summary: r.summary ?? null,
      url: r.url,
      source: r.source,
      tags: r.tags || [],
      publishedAt: r.published_at ?? null,
      matchScore: r.match_score ?? 0,
      rankPosition: r.rank_position ?? 0,
      recommendedAt: r.recommended_at,
      clickedAt: r.clicked_at ?? null,
      feedback: r.feedback ?? null
    }));
  },

  submitRecommendationFeedback: async (recommendationId: string, action: 'clicked' | 'liked' | 'disliked' | 'ignored') => {
    const token = await getToken();
    const res = await fetch(`${API_BASE_URL}/content/recommendations/${recommendationId}/feedback`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ action })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  getContentPreference: async () => {
    const token = await getToken();
    const res = await fetch(`${API_BASE_URL}/content/preference`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const p = await res.json();
    return {
      enabled: true,
      daily_limit: p.max_daily_recommendations ?? 1,
      preferred_sources: p.preferred_sources || [],
      quiet_hours_start: p.quiet_hours_start || null,
      quiet_hours_end: p.quiet_hours_end || null
    };
  },

  updateContentPreference: async (pref: {
    enabled: boolean;
    daily_limit: number;
    preferred_sources: string[];
    quiet_hours_start: string | null;
    quiet_hours_end: string | null;
  }) => {
    const token = await getToken();
    const payload: any = {
      content_recommendation_enabled: true,
      max_daily_recommendations: pref.daily_limit,
      preferred_sources: pref.preferred_sources
    };
    if (pref.quiet_hours_start !== undefined) payload.quiet_hours_start = pref.quiet_hours_start;
    if (pref.quiet_hours_end !== undefined) payload.quiet_hours_end = pref.quiet_hours_end;
    const res = await fetch(`${API_BASE_URL}/content/preference`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const p = await res.json();
    return {
      enabled: !!p.content_recommendation_enabled,
      daily_limit: p.max_daily_recommendations ?? 1,
      preferred_sources: p.preferred_sources || [],
      quiet_hours_start: p.quiet_hours_start || null,
      quiet_hours_end: p.quiet_hours_end || null
    };
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

  /**
   * 2.1 & 2.2 Streaming Message (Fast Path)
   * Endpoint: /api/v1/sse/message
   */
  sendMessageStream: async function* (text: string): AsyncGenerator<StreamEvent> {
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
      body: JSON.stringify({ message: text })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    if (!response.body) throw new Error("No response body");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const processedEvents = new Set<string>(); // 去重：防止重复处理相同事件
    let shouldStop = false;

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
        if (!trimmedLine.startsWith('data:')) continue;
        const cleanLine = trimmedLine.slice(5).trimStart();

        try {
            if (cleanLine === '[DONE]') {
              shouldStop = true;
              break;
            }
            
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
      if (shouldStop) break;
    }
  },

  getMemePreferences: async () => {
    const token = await getToken();
    const res = await fetch(`${API_BASE_URL}/memes/preferences`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  updateMemePreferences: async (payload: { meme_enabled: boolean }) => {
    const token = await getToken();
    const res = await fetch(`${API_BASE_URL}/memes/preferences`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  submitMemeFeedback: async (usageId: string, action: 'liked' | 'disliked' | 'ignored') => {
    const token = await getToken();
    const res = await fetch(`${API_BASE_URL}/memes/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ usage_id: usageId, reaction: action })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  /**
   * 4.3 Polling Memory Status (Slow Path / Fallback)
   * Endpoint: /api/v1/memories/{id}
   */
  pollMemoryStatus: (memoryId: string, onCommitted: () => void) => {
    if (USE_MOCK_DATA) {
      setTimeout(() => {
        onCommitted();
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
              onCommitted();
              return;
            } else if (data.status === 'deleted') {
                return; 
            }
        }
      } catch (e) {
        console.error("Polling error", e);
      }

      setTimeout(tick, delay);
      delay = Math.min(maxDelay, delay * 1.5);
    };

    tick();
  }
};
