export const Sender = {
  USER: 'user',
  AI: 'ai',
  SYSTEM: 'system'
} as const;

export type Sender = (typeof Sender)[keyof typeof Sender];

export const MemoryState = {
  PENDING: 'pending',
  COMMITTED: 'committed',
  DELETED: 'deleted',
  NONE: 'none'
} as const;

export type MemoryState = (typeof MemoryState)[keyof typeof MemoryState];

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
    imageUrl?: string | null;
    reacted?: 'liked' | 'ignored' | 'disliked' | null;
  };
}

export interface GraphNode {
  id: string;
  label: string;
  type: 'concept' | 'entity' | 'event';
  weight?: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  weight?: number;
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
  type: 'start' | 'text' | 'memory_pending' | 'done' | 'error' | 'meme';
  content?: string;
  session_id?: string;
  memory_id?: string;
  metadata?: any;
}

export interface MemoryStatusResponse {
  id: string;
  status: 'pending' | 'committed' | 'deleted';
}

export interface ProactiveMessage {
  id: string;
  trigger_type: string;
  content: string;
  status: string;
  created_at: string | null;
  sent_at: string | null;
  read_at: string | null;
  metadata: any;
}

export interface ProactivePreferences {
  proactive_enabled: boolean;
  morning_greeting_enabled: boolean;
  evening_greeting_enabled: boolean;
  silence_reminder_