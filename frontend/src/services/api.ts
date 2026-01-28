import type { Message, Sender, MemoryState, GraphData, AffinityPoint, StreamEvent, MemoryStatusResponse } from '../types';
import { MOCK_GRAPH_DATA_DAY_1, MOCK_GRAPH_DATA_DAY_15, MOCK_GRAPH_DATA_DAY_30, MOCK_AFFINITY_HISTORY } from '../constants';

// ============================================================================
// ⚠️ BACKEND INTEGRATION CONFIG (READY FOR PRODUCTION)
// ============================================================================

// 1. 关闭 Mock，连接真实后端
const USE_MOCK_DATA = false; 

// 2. 更新为后端 v1 接口地址
const API_BASE_URL = 'http://localhost:8000/api/v1'; 

// 3. 动态获取 Token
let cachedToken: string | null = null;

const getToken = async (): Promise<string> => {
  if (cachedToken) return cachedToken;
  
  try {
    const response = await fetch(`${API_BASE_URL}/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({})
    });
    if (response.ok) {
      const data = await response.json();
      cachedToken = data.access_token;
      return cachedToken;
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
    'KNOWS': '认识',
    'LIKES': '喜欢',
    'DISLIKES': '讨厌',
    'VISITED': '去过',
    'RELATES_TO': '相关',
    'FAMILY': '家人',
    'FRIEND': '朋友',
    'COLLEAGUE': '同事',
    'CONCERN': '关心'
  };
  
  return {
    nodes: backendData.nodes.map((n: any) => ({
      // 保留所有后端属性
      ...n,
      // 添加前端需要的映射字段
      label: n.name || n.label,
      weight: n.mention_count || n.weight || 10
    })),
    edges: backendData.edges.map((e: any) => {
      const weight = e.current_weight !== undefined ? e.current_weight : (e.weight || 1);
      const weightPercent = Math.round(weight * 100);
      const relationLabel = relationLabels[e.relation_type] || e.relation_type || 'related';
      return {
        // 保留所有后端属性
        ...e,
        // 添加前端需要的映射字段
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
  },

  /**
   * Get Dashboard Data
   * Endpoint: /api/v1/affinity/dashboard
   */
  getDashboard: async (): Promise<any> => {
    if (USE_MOCK_DATA) {
      await new Promise(resolve => setTimeout(resolve, 300));
      return {
        relationship: {
          state: 'friend',
          state_display: '朋友',
          score: 0.55,
          score_raw: 0.55,
          hearts: '💙💙💙'
        },
        days_known: 30,
        memories: { count: 15, can_view_details: true },
        top_topics: [
          { topic: '编程', count: 8 },
          { topic: '咖啡', count: 5 },
          { topic: 'AI', count: 3 }
        ],
        emotion_trend: [
          { date: '第1天', score: 10 },
          { date: '第15天', score: 35 },
          { date: '第30天', score: 55 }
        ],
        feedback: { likes: 12, dislikes: 2, saves: 5, favorites: 5 },
        health_reminder: null
      };
    }

    try {
      const token = await getToken();
      const response = await fetch(`${API_BASE_URL}/affinity/dashboard`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      return await response.json();
    } catch (e) {
      console.error("Failed to fetch dashboard", e);
      throw e;
    }
  },

  /**
   * Get Memories List
   * Endpoint: /api/v1/memories?limit=X
   */
  getMemories: async (limit: number): Promise<any[]> => {
    if (USE_MOCK_DATA) {
      await new Promise(resolve => setTimeout(resolve, 300));
      return [
        {
          id: 'mem_1',
          content: '小明喜欢喝咖啡',
          valence: 0.8,
          status: 'committed',
          created_at: new Date(Date.now() - 86400000 * 29).toISOString(),
          committed_at: new Date(Date.now() - 86400000 * 29).toISOString()
        },
        {
          id: 'mem_2',
          content: '小明是一名程序员',
          valence: 0.6,
          status: 'committed',
          created_at: new Date(Date.now() - 86400000 * 28).toISOString(),
          committed_at: new Date(Date.now() - 86400000 * 28).toISOString()
        },
        {
          id: 'mem_3',
          content: '小明经常深夜工作',
          valence: -0.2,
          status: 'committed',
          created_at: new Date(Date.now() - 86400000 * 15).toISOString(),
          committed_at: new Date(Date.now() - 86400000 * 15).toISOString()
        },
        {
          id: 'mem_4',
          content: '小明成功完成了项目上线',
          valence: 0.9,
          status: 'committed',
          created_at: new Date(Date.now() - 86400000 * 2).toISOString(),
          committed_at: new Date(Date.now() - 86400000 * 2).toISOString()
        },
        {
          id: 'mem_5',
          content: '小明对 AI 助手建立了信任',
          valence: 0.95,
          status: 'committed',
          created_at: new Date(Date.now() - 86400000).toISOString(),
          committed_at: new Date(Date.now() - 86400000).toISOString()
        }
      ];
    }

    try {
      const token = await getToken();
      const response = await fetch(`${API_BASE_URL}/memories?limit=${limit}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      return await response.json();
    } catch (e) {
      console.error("Failed to fetch memories", e);
      throw e;
    }
  },

  /**
   * Get Single Memory Detail
   * Endpoint: /api/v1/memories/{id}
   */
  getMemory: async (memoryId: string): Promise<any> => {
    if (USE_MOCK_DATA) {
      await new Promise(resolve => setTimeout(resolve, 200));
      return {
        id: memoryId,
        content: '这是一条详细的记忆内容',
        valence: 0.7,
        status: 'committed',
        created_at: new Date(Date.now() - 86400000).toISOString(),
        committed_at: new Date(Date.now() - 86400000).toISOString()
      };
    }

    try {
      const token = await getToken();
      const response = await fetch(`${API_BASE_URL}/memories/${memoryId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      return await response.json();
    } catch (e) {
      console.error("Failed to fetch memory", e);
      throw e;
    }
  },

  /**
   * Delete Multiple Memories
   * Endpoint: DELETE /api/v1/memories
   */
  deleteMemories: async (memoryIds: string[]): Promise<void> => {
    if (USE_MOCK_DATA) {
      await new Promise(resolve => setTimeout(resolve, 500));
      console.log('Mock: Deleted memories', memoryIds);
      return;
    }

    try {
      const token = await getToken();
      const response = await fetch(`${API_BASE_URL}/memories`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ memory_ids: memoryIds })
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    } catch (e) {
      console.error("Failed to delete memories", e);
      throw e;
    }
  },

  /**
   * Delete All Memories
   * Endpoint: DELETE /api/v1/memories/all
   */
  deleteAllMemories: async (): Promise<void> => {
    if (USE_MOCK_DATA) {
      await new Promise(resolve => setTimeout(resolve, 800));
      console.log('Mock: Deleted all memories');
      return;
    }

    try {
      const token = await getToken();
      const response = await fetch(`${API_BASE_URL}/memories/all`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    } catch (e) {
      console.error("Failed to delete all memories", e);
      throw e;
    }
  },

  /**
   * Content Recommendation: Get user preference
   * Endpoint: GET /api/v1/content/preference
   */
  getContentPreference: async () => {
    if (USE_MOCK_DATA) {
      return {
        enabled: false,
        daily_limit: 1,
        preferred_sources: [],
        quiet_hours_start: '22:00',
        quiet_hours_end: '08:00'
      };
    }

    try {
      const token = await getToken();
      const response = await fetch(`${API_BASE_URL}/content/preference`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      
      // 转换后端字段名到前端格式
      return {
        enabled: data.content_recommendation_enabled,
        daily_limit: data.max_daily_recommendations,
        preferred_sources: data.preferred_sources || [],
        quiet_hours_start: data.quiet_hours_start,
        quiet_hours_end: data.quiet_hours_end
      };
    } catch (e) {
      console.error("Failed to get content preference", e);
      throw e;
    }
  },

  /**
   * Content Recommendation: Update user preference
   * Endpoint: PUT /api/v1/content/preference
   */
  updateContentPreference: async (preference: {
    enabled?: boolean;
    daily_limit?: number;
    preferred_sources?: string[];
    quiet_hours_start?: string | null;
    quiet_hours_end?: string | null;
  }) => {
    if (USE_MOCK_DATA) {
      return {
        enabled: preference.enabled ?? false,
        daily_limit: preference.daily_limit ?? 1,
        preferred_sources: preference.preferred_sources ?? [],
        quiet_hours_start: preference.quiet_hours_start ?? '22:00',
        quiet_hours_end: preference.quiet_hours_end ?? '08:00'
      };
    }

    try {
      const token = await getToken();
      
      // 转换前端字段名到后端格式
      const payload: any = {};
      if (preference.enabled !== undefined) {
        payload.content_recommendation_enabled = preference.enabled;
      }
      if (preference.daily_limit !== undefined) {
        payload.max_daily_recommendations = preference.daily_limit;
      }
      if (preference.preferred_sources !== undefined) {
        payload.preferred_sources = preference.preferred_sources;
      }
      if (preference.quiet_hours_start !== undefined) {
        payload.quiet_hours_start = preference.quiet_hours_start;
      }
      if (preference.quiet_hours_end !== undefined) {
        payload.quiet_hours_end = preference.quiet_hours_end;
      }
      
      const response = await fetch(`${API_BASE_URL}/content/preference`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      
      // 转换后端字段名到前端格式
      return {
        enabled: data.content_recommendation_enabled,
        daily_limit: data.max_daily_recommendations,
        preferred_sources: data.preferred_sources || [],
        quiet_hours_start: data.quiet_hours_start,
        quiet_hours_end: data.quiet_hours_end
      };
    } catch (e) {
      console.error("Failed to update content preference", e);
      throw e;
    }
  },

  /**
   * Content Recommendation: Get today's recommendations
   * Endpoint: GET /api/v1/content/recommendations
   */
  getContentRecommendations: async () => {
    if (USE_MOCK_DATA) {
      return [];
    }

    try {
      const token = await getToken();
      const response = await fetch(`${API_BASE_URL}/content/recommendations`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      
      // 转换后端字段名到前端格式
      return data.map((item: any) => ({
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
    } catch (e) {
      console.error("Failed to get content recommendations", e);
      throw e;
    }
  },

  /**
   * Content Recommendation: Submit feedback
   * Endpoint: POST /api/v1/content/recommendations/{id}/feedback
   */
  submitRecommendationFeedback: async (
    recommendationId: string,
    action: 'clicked' | 'liked' | 'disliked' | 'ignored'
  ) => {
    if (USE_MOCK_DATA) {
      return { success: true, message: 'Feedback recorded' };
    }

    try {
      const token = await getToken();
      const response = await fetch(
        `${API_BASE_URL}/content/recommendations/${recommendationId}/feedback`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({ action })
        }
      );
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      return await response.json();
    } catch (e) {
      console.error("Failed to submit feedback", e);
      throw e;
    }
  }
};
