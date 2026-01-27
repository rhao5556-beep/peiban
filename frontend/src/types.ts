export enum Sender {
  USER = 'user',
  AI = 'ai',
  SYSTEM = 'system'
}

export enum MemoryState {
  PENDING = 'pending',     // 正在处理/短期记忆
  COMMITTED = 'committed', // 已存入长期记忆/图谱
  DELETED = 'deleted',     // 已遗忘/删除
  NONE = 'none'
}

export interface Message {
  id: string;
  text: string;
  sender: Sender;
  timestamp: number;
  memoryState?: MemoryState; // For AI messages primarily
  memoryId?: string; // To track backend memory ID for polling
  isTyping?: boolean; // For UI feedback
}

export interface GraphNode {
  id: string;
  name: string;  // 后端返回的字段名
  label?: string;  // 用于显示，从 name 映射
  type: string;  // person, place, preference, event, concept 等
  mention_count?: number;
  weight?: number;  // 用于可视化，从 mention_count 映射
  first_mentioned_at?: string;
  last_mentioned_at?: string;
}

export interface GraphEdge {
  id: string;
  source_id: string;  // 后端返回的字段名
  target_id: string;  // 后端返回的字段名
  source?: string;  // 用于 Cytoscape，从 source_id 映射
  target?: string;  // 用于 Cytoscape，从 target_id 映射
  relation_type: string;  // 后端返回的字段名
  label?: string;  // 用于显示，从 relation_type 映射
  weight: number;
  current_weight?: number;
  decay_rate?: number;
  created_at?: string;
  updated_at?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface AffinityPoint {
  timestamp: string; // ISO Date or formatted string like "Day 1"
  value: number; // 0-100
  event?: string; // Optional label for key events
}

export interface UserState {
  isConnected: boolean;
  affinity: number;
  currentDay: number;
}

// --- New Types for Backend Integration ---

export interface StreamEvent {
  type: 'start' | 'text' | 'memory_pending' | 'memory_committed' | 'done' | 'error';
  content?: string;
  session_id?: string;
  memory_id?: string;
  metadata?: any;
}

export interface MemoryStatusResponse {
  id: string;
  status: 'pending' | 'committed' | 'deleted';
}
