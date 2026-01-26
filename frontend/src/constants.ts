import type { GraphData, AffinityPoint } from './types';

// Mock Data for Phase 6.3 Demo (Translated)
export const MOCK_GRAPH_DATA_DAY_1: GraphData = {
  nodes: [
    { id: 'user', label: '用户 (小明)', type: 'entity', weight: 10 },
    { id: 'coffee', label: '咖啡', type: 'concept', weight: 5 },
    { id: 'coding', label: '编程', type: 'event', weight: 8 },
  ],
  edges: [
    { id: 'e1', source: 'user', target: 'coffee', label: '喜欢' },
    { id: 'e2', source: 'user', target: 'coding', label: '从事' },
  ]
};

export const MOCK_GRAPH_DATA_DAY_15: GraphData = {
  nodes: [
    ...MOCK_GRAPH_DATA_DAY_1.nodes,
    { id: 'ai', label: 'AI 助手', type: 'entity', weight: 10 },
    { id: 'late_night', label: '深夜', type: 'event', weight: 6 },
    { id: 'anxiety', label: '焦虑', type: 'concept', weight: 4 },
  ],
  edges: [
    ...MOCK_GRAPH_DATA_DAY_1.edges,
    { id: 'e3', source: 'ai', target: 'user', label: '支持' },
    { id: 'e4', source: 'user', target: 'late_night', label: '工作于' },
    { id: 'e5', source: 'late_night', target: 'anxiety', label: '引发' },
  ]
};

export const MOCK_GRAPH_DATA_DAY_30: GraphData = {
  nodes: [
    ...MOCK_GRAPH_DATA_DAY_15.nodes,
    { id: 'project_launch', label: '项目上线', type: 'event', weight: 15 },
    { id: 'success', label: '成功', type: 'concept', weight: 12 },
    { id: 'trust', label: '信任', type: 'concept', weight: 20 },
  ],
  edges: [
    ...MOCK_GRAPH_DATA_DAY_15.edges,
    { id: 'e6', source: 'user', target: 'project_launch', label: '完成了' },
    { id: 'e7', source: 'project_launch', target: 'success', label: '导致' },
    { id: 'e8', source: 'user', target: 'trust', label: '感觉到' },
  ]
};

export const MOCK_AFFINITY_HISTORY: AffinityPoint[] = [
  { timestamp: '第1天', value: 10, event: '初次相识' },
  { timestamp: '第5天', value: 25, event: '' },
  { timestamp: '第10天', value: 40, event: '深度交谈' },
  { timestamp: '第15天', value: 35, event: '发生冲突' },
  { timestamp: '第20天', value: 55, event: '' },
  { timestamp: '第25天', value: 70, event: '相互安慰' },
  { timestamp: '第30天', value: 85, event: '建立羁绊' },
];