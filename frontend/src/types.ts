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
  meme?: {
    memeId: string;
    usageId: string;
    description: string;
    imageUrl?: string;
  };
}

export interface GraphNode {
  id: string;
  label: string;
  type: 'concept' | 'entity' | 'event';
  weight?: number;
  properties?: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  weight?: number;
  properties?: Record<string, unknown>;
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
  type: 'start' | 'text' | 'memory_pending' | 'meme' | 'done' | 'error';
  content?: string;
  session_id?: string;
  memory_id?: string;
  metadata?: any;
}

export interface MemoryStatusResponse {
  id: string;
  status: 'pending' | 'committed' | 'deleted';
}
