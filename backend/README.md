# Affinity - 情感化 AI 陪伴记忆系统

基于 GraphRAG 与好感度演化的长期记忆系统，让 AI 像人一样理解关系、偏好与情感。

## 核心特性

- **动态记忆图谱**: Neo4j 存储实体关系，边权重随时间衰减，提及时刷新
- **好感度系统**: 量化 AI 对用户的情感倾向，影响检索策略和对话语气
- **Hybrid Retrieval**: Vector + Graph 混合检索，结合好感度 Re-rank
- **联网搜索回退**: 当无相关长期记忆时，可用 Tavily 补充通用知识（默认关闭）
- **流式输出**: SSE 支持实时对话体验
- **最终一致性**: Outbox 模式确保数据一致性

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端框架 | FastAPI |
| 图数据库 | Neo4j |
| 向量数据库 | Milvus |
| 关系数据库 | PostgreSQL + pgvector |
| 消息队列 | Redis |
| 任务调度 | Celery + Beat |
| 前端 | React + TypeScript |
| 图可视化 | Cytoscape.js |

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repo-url>
cd affinity

# 复制环境变量
cp .env.example .env
# 编辑 .env 填入必要配置
```

可选功能（默认关闭）：

- 联网搜索（Tavily）：设置 `WEB_SEARCH_ENABLED=true`，并填写 `TAVILY_API_KEY`

### 2. 启动服务

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f api
```

### 3. 访问服务

- API 文档: http://localhost:8000/docs
- Flower 监控: http://localhost:5555
- Neo4j Browser: http://localhost:7474

## API 示例

### 获取 Token

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user"}'
```

### 发送消息

```bash
curl -X POST http://localhost:8000/api/v1/conversation/message \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "我妈妈最近身体不太好"}'
```

### 流式对话 (SSE)

```bash
curl -X POST http://localhost:8000/api/v1/stream/message \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'
```

## 项目结构

```
affinity/
├── app/
│   ├── api/              # API 端点
│   ├── core/             # 核心配置
│   ├── middleware/       # 中间件
│   ├── models/           # 数据模型
│   ├── services/         # 业务服务
│   └── worker/           # Celery 任务
├── tests/                # 测试
├── scripts/              # 脚本
├── docker-compose.yml    # Docker 配置
└── requirements.txt      # 依赖
```

## 测试

```bash
# 运行所有测试
pytest

# 运行属性测试
pytest tests/test_properties.py -v

# 运行覆盖率
pytest --cov=app --cov-report=html
```

## 正确性属性

系统实现了以下正确性属性（详见 design.md）：

1. **图谱数据往返一致性**
2. **边权重衰减公式正确性**
3. **好感度分数边界不变量**
4. **好感度状态映射正确性**
5. **检索结果包含完整分数分解**
6. **生成结果包含必要元数据**
7. **GDPR 删除后不可检索**
8. **删除审计 JSON 完整性**
9. **最终一致性 with SLO**
10. **好感度变化可追溯**
11. **并发写幂等性**
12. **Outbox 本地事务原子性**
13. **删除可验证性**

## SLO 指标

| 指标 | 目标 |
|------|------|
| Outbox Lag (P50) | < 2s |
| Outbox Lag (P95) | < 30s |
| 数据不一致率 | < 1% |

## License

MIT
