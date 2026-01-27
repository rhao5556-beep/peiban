import { useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';
import AffinityChart from './AffinityChart';
import { Download, Eye, RefreshCw, ShieldAlert, Trash2 } from 'lucide-react';
import type { AffinityPoint } from '../types';

type DashboardResponse = {
  relationship?: {
    state?: string;
    state_display?: string;
    score?: number;
    score_raw?: number;
    hearts?: string;
  };
  days_known?: number;
  memories?: { count?: number; can_view_details?: boolean };
  top_topics?: Array<{ topic: string; count: number }>;
  emotion_trend?: Array<{ date: string; score: number }>;
  feedback?: { likes?: number; dislikes?: number; saves?: number; favorites?: number };
  health_reminder?: any;
};

type MemoryItem = {
  id: string;
  content: string;
  valence?: number | null;
  status: string;
  created_at: string;
  committed_at?: string | null;
};

function formatDateTime(value?: string | null) {
  if (!value) return '-';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString();
}

function downloadJson(filename: string, data: unknown) {
  const dataStr = 'data:application/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(data, null, 2));
  const link = document.createElement('a');
  link.download = filename;
  link.href = dataStr;
  link.click();
}

export function AffinityDashboard(props: {
  affinityHistory: AffinityPoint[];
  currentDay: number;
  onRefreshGraph?: () => void | Promise<void>;
}) {
  const { affinityHistory, currentDay, onRefreshGraph } = props;

  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [detail, setDetail] = useState<MemoryItem | null>(null);

  const selectedList = useMemo(() => Object.keys(selectedIds).filter((id) => selectedIds[id]), [selectedIds]);
  const canViewDetails = dashboard?.memories?.can_view_details ?? true;

  const load = async () => {
    setBusy(true);
    setError(null);
    try {
      const [dash, mems] = await Promise.all([api.getDashboard(), api.getMemories(50)]);
      setDashboard(dash);
      setMemories(mems);
      setSelectedIds({});
    } catch (e: any) {
      const msg = e?.message ?? '加载失败';
      setError(msg.includes('Failed to fetch') ? '无法连接后端（网络/跨域/地址配置问题）。请确认后端已启动，或配置 VITE_API_BASE_URL。' : msg);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const openDetail = async (memoryId: string) => {
    setDetailId(memoryId);
    setDetail(null);
    setError(null);
    if (!canViewDetails) return;
    try {
      const res = await api.getMemory(memoryId);
      setDetail(res);
    } catch (e: any) {
      setError(e?.message ?? '加载记忆详情失败');
    }
  };

  const toggleSelectAll = (checked: boolean) => {
    if (!checked) {
      setSelectedIds({});
      return;
    }
    const next: Record<string, boolean> = {};
    for (const m of memories) next[m.id] = true;
    setSelectedIds(next);
  };

  const deleteSelected = async () => {
    if (selectedList.length === 0) return;
    const ok = window.confirm(`确定删除选中的 ${selectedList.length} 条记忆吗？删除后将标记为已遗忘。`);
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteMemories(selectedList);
      await load();
      onRefreshGraph?.();
    } catch (e: any) {
      setError(e?.message ?? '删除失败');
    } finally {
      setBusy(false);
    }
  };

  const deleteAll = async () => {
    const ok = window.confirm('确定删除全部记忆吗？该操作不可撤销。');
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteAllMemories();
      await load();
      onRefreshGraph?.();
    } catch (e: any) {
      setError(e?.message ?? '删除失败');
    } finally {
      setBusy(false);
    }
  };

  const relationshipTitle = dashboard?.relationship?.state_display ?? '关系状态';
  const relationshipScoreRaw = dashboard?.relationship?.score_raw ?? dashboard?.relationship?.score ?? 0;
  const relationshipScore =
    relationshipScoreRaw <= 1 ? Math.round(relationshipScoreRaw * 100) : Math.round(relationshipScoreRaw);
  const hearts = dashboard?.relationship?.hearts ?? '';
  const daysKnown = dashboard?.days_known ?? 0;
  const dashboardCount = dashboard?.memories?.count;
  const memoryCount = dashboardCount && dashboardCount > 0 ? dashboardCount : memories.length;

  const likes = dashboard?.feedback?.likes ?? 0;
  const dislikes = dashboard?.feedback?.dislikes ?? 0;
  const saves = dashboard?.feedback?.saves ?? dashboard?.feedback?.favorites ?? 0;

  const healthReminderMessage =
    dashboard?.health_reminder && typeof dashboard.health_reminder === 'object'
      ? dashboard.health_reminder.message
      : dashboard?.health_reminder;

  return (
    <div className="flex-grow p-6 overflow-auto">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-lg font-semibold text-gray-900">关系仪表盘</div>
            <div className="text-xs text-gray-500 mt-1">包含关系状态、记忆管理与数据导出</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => downloadJson(`dashboard-day-${currentDay}.json`, { dashboard, memories })}
              className="px-3 py-2 rounded-md bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 flex items-center gap-2"
              disabled={busy}
              title="导出仪表盘数据（JSON）"
            >
              <Download size={16} />
              <span className="text-sm">导出数据</span>
            </button>
            <button
              onClick={load}
              className="px-3 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-500 flex items-center gap-2"
              disabled={busy}
              title="刷新"
            >
              <RefreshCw size={16} />
              <span className="text-sm">{busy ? '刷新中' : '刷新'}</span>
            </button>
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-lg border border-red-200 bg-red-50 text-red-700 text-sm">{error}</div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
            <div className="text-xs text-gray-500">关系状态</div>
            <div className="mt-2 flex items-end justify-between gap-2">
              <div>
                <div className="text-lg font-semibold text-gray-900">{relationshipTitle}</div>
            <div className="text-xs text-gray-500 mt-1">分数 {relationshipScore}</div>
              </div>
              <div className="text-lg">{hearts}</div>
            </div>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
            <div className="text-xs text-gray-500">认识天数</div>
            <div className="mt-2 text-2xl font-semibold text-gray-900">{daysKnown}</div>
            <div className="text-xs text-gray-500 mt-1">天</div>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
            <div className="text-xs text-gray-500">AI 记住的关键信息</div>
            <div className="mt-2 text-2xl font-semibold text-gray-900">{memoryCount}</div>
            <div className="text-xs text-gray-500 mt-1">条</div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 min-h-[320px]">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold text-gray-900">情感亲密度趋势</div>
                <div className="text-xs text-gray-500 mt-1">用于观察关系变化与关键节点</div>
              </div>
            </div>
            <div className="mt-3">
              <AffinityChart data={affinityHistory} currentDay={currentDay} />
            </div>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
            <div className="text-sm font-semibold text-gray-900">反馈统计</div>
            <div className="text-xs text-gray-500 mt-1">用于观察显式反馈信号</div>
            <div className="mt-4 grid grid-cols-3 gap-3">
              <div className="p-3 rounded-lg bg-gray-50 border border-gray-200">
                <div className="text-xs text-gray-500">点赞</div>
                <div className="text-lg font-semibold text-gray-900 mt-1">{likes}</div>
              </div>
              <div className="p-3 rounded-lg bg-gray-50 border border-gray-200">
                <div className="text-xs text-gray-500">点踩</div>
                <div className="text-lg font-semibold text-gray-900 mt-1">{dislikes}</div>
              </div>
              <div className="p-3 rounded-lg bg-gray-50 border border-gray-200">
                <div className="text-xs text-gray-500">收藏</div>
                <div className="text-lg font-semibold text-gray-900 mt-1">{saves}</div>
              </div>
            </div>
            {healthReminderMessage ? (
              <div className="mt-4 p-3 rounded-lg border border-amber-200 bg-amber-50 text-amber-900 flex items-start gap-2">
                <ShieldAlert size={16} className="mt-0.5 flex-shrink-0" />
                <div className="text-sm">{healthReminderMessage}</div>
              </div>
            ) : null}
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-4 border-b border-gray-200 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-gray-900">记忆管理</div>
              <div className="text-xs text-gray-500 mt-1">查看、删除与导出记忆</div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => downloadJson(`memories-day-${currentDay}.json`, memories)}
                className="px-3 py-2 rounded-md bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                disabled={busy}
                title="导出记忆（JSON）"
              >
                <Download size={16} />
                <span className="text-sm">下载记忆</span>
              </button>
              <button
                onClick={deleteSelected}
                className="px-3 py-2 rounded-md bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 flex items-center gap-2 disabled:opacity-50"
                disabled={busy || selectedList.length === 0}
                title="删除选中的记忆"
              >
                <Trash2 size={16} />
                <span className="text-sm">删除选中</span>
              </button>
              <button
                onClick={deleteAll}
                className="px-3 py-2 rounded-md bg-red-600 text-white hover:bg-red-500 flex items-center gap-2 disabled:opacity-50"
                disabled={busy || memories.length === 0}
                title="删除全部记忆"
              >
                <Trash2 size={16} />
                <span className="text-sm">删除全部</span>
              </button>
            </div>
          </div>

          <div className="overflow-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200 text-gray-600">
                <tr>
                  <th className="p-3 text-left w-10">
                    <input
                      type="checkbox"
                      checked={memories.length > 0 && selectedList.length === memories.length}
                      onChange={(e) => toggleSelectAll(e.target.checked)}
                      disabled={busy || memories.length === 0}
                    />
                  </th>
                  <th className="p-3 text-left">内容</th>
                  <th className="p-3 text-left w-28">状态</th>
                  <th className="p-3 text-left w-44">创建时间</th>
                  <th className="p-3 text-left w-24">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {memories.map((m) => (
                  <tr key={m.id} className="hover:bg-gray-50">
                    <td className="p-3">
                      <input
                        type="checkbox"
                        checked={!!selectedIds[m.id]}
                        onChange={(e) => setSelectedIds((prev) => ({ ...prev, [m.id]: e.target.checked }))}
                        disabled={busy}
                      />
                    </td>
                    <td className="p-3 text-gray-900 max-w-[520px] truncate" title={m.content}>
                      {m.content}
                    </td>
                    <td className="p-3 text-gray-600">{m.status}</td>
                    <td className="p-3 text-gray-600">{formatDateTime(m.created_at)}</td>
                    <td className="p-3">
                      <button
                        onClick={() => openDetail(m.id)}
                        className="px-2 py-1 rounded-md bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 inline-flex items-center gap-1 disabled:opacity-50"
                        disabled={busy || !canViewDetails}
                        title={canViewDetails ? '查看详情' : '当前不允许查看详情'}
                      >
                        <Eye size={14} />
                        <span className="text-xs">查看</span>
                      </button>
                    </td>
                  </tr>
                ))}
                {memories.length === 0 && (
                  <tr>
                    <td className="p-6 text-center text-gray-500" colSpan={5}>
                      暂无记忆
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {detailId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/30">
          <div className="w-full max-w-2xl bg-white rounded-xl shadow-xl border border-gray-200 overflow-hidden">
            <div className="p-4 border-b border-gray-200 flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-900">记忆详情</div>
              <button
                className="px-3 py-2 rounded-md bg-white border border-gray-200 text-gray-700 hover:bg-gray-50"
                onClick={() => {
                  setDetailId(null);
                  setDetail(null);
                }}
              >
                关闭
              </button>
            </div>
            <div className="p-4 space-y-3">
              {!canViewDetails ? (
                <div className="p-3 rounded-lg border border-amber-200 bg-amber-50 text-amber-900">
                  当前策略不允许查看记忆详情。
                </div>
              ) : detail ? (
                <>
                  <div className="text-xs text-gray-500">ID</div>
                  <div className="font-mono text-xs text-gray-700 break-all">{detail.id}</div>
                  <div className="text-xs text-gray-500">内容</div>
                  <div className="text-sm text-gray-900 whitespace-pre-wrap">{detail.content}</div>
                  <div className="grid grid-cols-2 gap-3 pt-2">
                    <div className="p-3 rounded-lg bg-gray-50 border border-gray-200">
                      <div className="text-xs text-gray-500">状态</div>
                      <div className="text-sm text-gray-900 mt-1">{detail.status}</div>
                    </div>
                    <div className="p-3 rounded-lg bg-gray-50 border border-gray-200">
                      <div className="text-xs text-gray-500">情绪值</div>
                      <div className="text-sm text-gray-900 mt-1">{detail.valence ?? '-'}</div>
                    </div>
                    <div className="p-3 rounded-lg bg-gray-50 border border-gray-200">
                      <div className="text-xs text-gray-500">创建时间</div>
                      <div className="text-sm text-gray-900 mt-1">{formatDateTime(detail.created_at)}</div>
                    </div>
                    <div className="p-3 rounded-lg bg-gray-50 border border-gray-200">
                      <div className="text-xs text-gray-500">写入时间</div>
                      <div className="text-sm text-gray-900 mt-1">{formatDateTime(detail.committed_at)}</div>
                    </div>
                  </div>
                </>
              ) : (
                <div className="text-sm text-gray-600">加载中…</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AffinityDashboard;
