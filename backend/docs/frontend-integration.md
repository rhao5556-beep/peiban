# Affinity 前后端对接 README（Phase 6 · MVP）

本文档定义了 Affinity 情感化 AI 陪伴系统在 **前端可视化与交互阶段（Phase 6）** 的后端接口契约、已知限制与前端补偿策略（Polling Fallback）。

**目标**：在不阻塞后端架构演进的前提下，让前端完整跑通 UI / Demo。

---

## 1. 架构背景（重要）

系统采用 **Fast Path / Slow Path + Outbox Pattern**：

- **Fast Path**：对话生成、流式输出（低延迟，SSE）
- **Slow Path**：记忆写入（实体抽取、图谱 / 向量存储，异步 Worker）

👉 **结果**：前端可以立刻看到回复，但"记忆是否真正写入完成"是 **最终一致性（Eventually Consistent）**

因此，前端必须支持 `Pending → Committed` 的状态演进。

---

## 2. SSE 对话接口（核心）

### 2.1 接口定义

| 项目 | 值 |
|------|-----|
| URL | `POST /api/v1/sse/message` |
| Headers | `Authorization: Bearer <JWT_TOKEN>`<br>`Content-Type: application/json` |

**Body**:
```json
{
  "message": "用户消息",
  "session_id": "可选，会话ID",
  "idempotency_key": "可选，幂等键"
}
```

### 2.2 SSE 事件格式（逐行 JSON）

⚠️ **注意**：这是 `POST + Streaming Response`，浏览器不能直接用 `EventSource`，请使用 `fetch + ReadableStream`

```json
{"type": "start", "session_id": "xxx"}
{"type": "text", "content": "你"}
{"type": "text", "content": "好"}
{"type": "text", "content": "呀"}
{"type": "memory_pending", "memory_id": "mem_123", "metadata": {...}}
{"type": "done", "metadata": {...}}
{"type": "error", "content": "错误信息"}
```

### 2.3 已知限制（MVP 阶段）

❌ **当前不会推送** `{"type": "memory_committed", "memory_id": "..."}`

**原因**：
- 记忆写入在 Worker 中完成
- SSE 连接通常在回复结束后已关闭

👉 **前端必须使用 Polling 补偿**（见第 4 节）

---

## 3. 图谱数据接口（Cytoscape）

### 3.1 获取当前图谱

```
GET /api/v1/graph/
Authorization: Bearer <token>
```

**响应示例**:
```json
{
  "nodes": [
    {
      "id": "entity_1",
      "name": "妈妈",
      "type": "person",
      "mention_count": 5
    }
  ],
  "edges": [
    {
      "id": "edge_1",
      "source_id": "user_1",
      "target_id": "entity_1",
      "relation_type": "family",
      "weight": 0.85
    }
  ]
}
```

### 3.2 前端必须做的 Cytoscape 转换

```javascript
function toCytoscape(data) {
  return {
    nodes: data.nodes.map(n => ({
      data: {
        id: n.id,
        label: n.name,
        type: n.type
      }
    })),
    edges: data.edges.map(e => ({
      data: {
        id: e.id,
        source: e.source_id,
        target: e.target_id,
        weight: e.weight
      }
    }))
  };
}
```

📌 后端字段保持业务语义（`source_id`），前端负责适配 UI 库。

### 3.3 图谱时间轴

```
GET /api/v1/graph/timeline?days=30&interval=day
```

返回 `List[GraphSnapshot]`，每个快照包含该时间点的图谱状态。

---

## 4. 记忆状态更新（关键：Polling Fallback）

### 4.1 查询单条记忆状态接口

```
GET /api/v1/memories/{memory_id}
Authorization: Bearer <token>
```

**返回**:
```json
{
  "id": "mem_123",
  "content": "记忆内容",
  "status": "pending" | "committed" | "deleted",
  "created_at": "2024-01-01T00:00:00",
  "committed_at": null
}
```

### 4.2 前端必须实现的逻辑（强制）

**状态机**:
```
SSE memory_pending
        ↓
UI: "正在记忆…"
        ↓
轮询 /api/v1/memories/{id}
        ↓
status == committed
        ↓
UI: "已记住" + 刷新图谱
```

### 4.3 推荐 Polling 实现（带退避）

```javascript
function pollMemoryStatus(memoryId, token, onCommitted) {
  let delay = 3000;
  const maxDelay = 10000;
  const timeout = 30000;
  const start = Date.now();

  async function tick() {
    if (Date.now() - start > timeout) return;

    const res = await fetch(`/api/v1/memories/${memoryId}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    const data = await res.json();

    if (data.status === "committed") {
      onCommitted(data);
      return;
    }

    setTimeout(tick, delay);
    delay = Math.min(maxDelay, delay * 1.5);
  }

  tick();
}
```

---

## 5. 好感度接口

### 5.1 获取当前好感度

```
GET /api/v1/affinity/
Authorization: Bearer <token>
```

**返回**:
```json
{
  "user_id": "xxx",
  "score": 0.65,
  "state": "close_friend",
  "updated_at": "2024-01-30T12:00:00"
}
```

### 5.2 获取好感度历史（用于曲线图）

```
GET /api/v1/affinity/history?days=30
Authorization: Bearer <token>
```

**返回**:
```json
[
  {
    "id": "xxx",
    "old_score": 0.5,
    "new_score": 0.52,
    "delta": 0.02,
    "trigger_event": "conversation",
    "created_at": "2024-01-01T00:00:00"
  }
]
```

---

## 6. 认证说明（非常重要）

所有接口都需要：
```
Authorization: Bearer <JWT>
```

⚠️ **注意**：浏览器 `EventSource` 无法设置 Header

**当前推荐**：
- ✅ `fetch + ReadableStream`
- 或后续升级 WebSocket

### 6.1 获取 Token

```
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "user",
  "password": "pass"
}
```

---

## 7. 错误响应格式

所有 API 错误返回统一格式：

```json
{
  "detail": "错误描述"
}
```

**常见 HTTP 状态码**:

| 状态码 | 含义 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | Token 无效/过期 |
| 404 | 资源不存在 |
| 429 | 请求限流 |
| 500 | 服务器内部错误 |

---

## 8. CORS 配置

后端已配置 CORS 中间件，支持跨域请求。

开发环境允许所有 origin，生产环境需配置 `CORS_ORIGINS` 环境变量。

---

## 9. 前端 UI 行为约定（Phase 6）

### 对话界面
- 流式文字显示（打字机效果）
- `memory_pending` 时显示：⏳ "正在记忆…"
- `committed` 后显示：✅ "已记住"

### 图谱界面
- `committed` 后刷新图谱
- 支持时间轴 / 演化视图（如果启用）

---

## 10. 已知待改进（已入 Backlog）

不影响 Phase 6 交付：

- [ ] Worker → Redis Pub/Sub
- [ ] SSE / WebSocket Broker
- [ ] 主动推送 `memory_committed`
- [ ] 轮询降级为 fallback

---

## 11. MVP 原则声明

- **Outbox + 最终一致性** 是刻意的工程选择
- **Polling** 是客户端消费最终一致性的标准模式
- Phase 6 的目标是：**可用、可演示、可证明架构正确**

---

## 12. 一句话总结

> 前端现在就可以跑起来。后端的异步与一致性复杂度，没有被隐藏，而是被正确地建模并显性处理。

---

## API 速查表

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/auth/login` | POST | 获取 JWT Token |
| `/api/v1/sse/message` | POST | SSE 流式对话 |
| `/api/v1/conversation/message` | POST | 同步对话（非流式） |
| `/api/v1/memories/` | GET | 记忆列表 |
| `/api/v1/memories/{id}` | GET | 单条记忆状态 |
| `/api/v1/memories/` | DELETE | 删除记忆（GDPR） |
| `/api/v1/graph/` | GET | 获取图谱 |
| `/api/v1/graph/timeline` | GET | 图谱时间轴 |
| `/api/v1/affinity/` | GET | 当前好感度 |
| `/api/v1/affinity/history` | GET | 好感度历史 |

---

*文档版本: v1.0 | 更新时间: 2024-12-30*

---

## 附录：给前端 Agent 的话术（可直接复制）

```
我这里有前端完整 React demo（已包含 fetch streaming、memory_pending 处理与 polling badge），
请按以下接口实现后端：

1. POST /api/v1/sse/message 
   — 返回逐行 JSON 流（type: text|memory_pending|done|error）
   — 前端使用 fetch + ReadableStream

2. GET /api/v1/memories/{memory_id} 
   — 返回 {id, status: pending|committed|deleted, created_at, committed_at}
   — 必须实现，供前端 polling

3. GET /api/v1/graph/ 
   — 返回 {nodes:[], edges:[]}
   — edges 使用 source_id/target_id，前端会转换

所有请求需 Authorization: Bearer <JWT>。
后端可先用 demo 数据，实时推送 memory_committed 为加分项（非 MVP 必需）。
```
