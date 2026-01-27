# 🔑 API 密钥配置指南

**更新时间**: 2026-01-19

---

## 📋 密钥清单

| 密钥名称 | 是否必需 | 是否花钱 | 说明 |
|---------|---------|---------|------|
| `OPENAI_API_KEY` | ✅ 必需 | ✅ 需要 | 硅基流动 API Key（对话功能） |
| `JWT_SECRET` | ✅ 必需 | ❌ 免费 | 自己生成的随机字符串 |
| `WEIBO_API_KEY` | ❌ 不需要 | ❌ 免费 | 我们用 RSSHub，不需要这个 |
| `MINIO_*` | ❌ 不需要 | ❌ 免费 | 目前未使用对象存储 |

---

## 1. OPENAI_API_KEY - 硅基流动 API Key

### ✅ 当前配置（已正确）

```env
OPENAI_API_KEY=sk-xyuqotucvlvthyssvbnkqxtwhbylgummomshkqvfecaueghcx
OPENAI_API_BASE=https://api.siliconflow.cn/v1
OPENAI_MODEL=deepseek-ai/DeepSeek-V3
```

### 说明

- **用途**: AI 对话、实体提取、冲突解决
- **提供商**: 硅基流动 (SiliconFlow)
- **模型**: DeepSeek-V3
- **费用**: 按使用量计费（非常便宜）
- **获取方式**: https://siliconflow.cn

### 如何获取

1. 访问 https://siliconflow.cn
2. 注册账号
3. 进入控制台
4. 创建 API Key
5. 复制 Key 到 `.env` 文件

### 费用参考

- DeepSeek-V3: 约 ¥0.0014/1K tokens（输入）
- 非常便宜，日常使用几乎可以忽略不计

---

## 2. JWT_SECRET - JWT 加密密钥

### ❌ 当前配置（需要生成）

```env
# 当前是占位符，需要替换
JWT_SECRET=your-secret-key-here-change-in-production
```

### 说明

- **用途**: 加密用户登录 Token
- **费用**: ❌ 完全免费（自己生成）
- **安全性**: 生产环境必须使用强随机字符串

### 如何生成

#### 方法 1: 使用 Python（推荐）
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### 方法 2: 使用 PowerShell
```powershell
[Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Maximum 256 }))
```

#### 方法 3: 在线生成
访问: https://randomkeygen.com/

### 示例配置

```env
# 生成的随机密钥（示例）
JWT_SECRET=nlNLbV62eKjedCT3tOacNEVE13cBRC25I61KtQcTMiw
```

**⚠️ 重要**: 
- 生产环境必须使用强随机字符串
- 不要使用示例中的密钥
- 不要将密钥提交到 Git 仓库

---

## 3. WEIBO_API_KEY - 微博 API Key

### ✅ 不需要配置！

```env
# 这个配置项可以删除或留空
# WEIBO_API_KEY=
```

### 说明

- **用途**: 原本用于抓取微博热搜
- **实际方案**: 我们使用 **RSSHub**（完全免费）
- **费用**: ❌ 完全免费
- **是否需要**: ❌ **不需要！**

### 我们的实现方式

我们使用 **RSSHub** 提供的免费 RSS 订阅：

```python
# 微博热搜RSS源（通过RSSHub）
WEIBO_HOT_RSS = "https://rsshub.app/weibo/search/hot"
```

**RSSHub 特点**:
- ✅ 完全免费
- ✅ 无需注册
- ✅ 无需 API Key
- ✅ 开源项目
- ✅ 支持多个平台（微博、知乎、B站等）

### RSSHub 支持的平台

我们使用的 RSS 源：

```python
# 内容推荐
"https://rsshub.app/36kr/news"           # 36氪新闻
"https://rsshub.app/ithome/ranking"     # IT之家排行
"https://rsshub.app/geekpark"           # 极客公园
"https://rsshub.app/thepaper/featured"  # 澎湃新闻
"https://rsshub.app/github/trending/daily"  # GitHub 趋势
"https://rsshub.app/v2ex/hot"           # V2EX 热门
"https://rsshub.app/douban/movie/weekly"    # 豆瓣电影

# 表情包/热搜
"https://rsshub.app/weibo/search/hot"   # 微博热搜
"https://rsshub.app/zhihu/hotlist"      # 知乎热榜
"https://rsshub.app/bilibili/ranking/0/3/1"  # B站排行榜
```

**结论**: 不需要任何微博 API Key！

---

## 4. MINIO_* - MinIO 对象存储

### ✅ 不需要配置！

```env
# 这些配置项可以删除或留空
# MINIO_ENDPOINT=
# MINIO_ACCESS_KEY=
# MINIO_SECRET_KEY=
# MINIO_BUCKET=
```

### 说明

- **用途**: 存储图片、文件等
- **当前状态**: ❌ **系统未使用**
- **费用**: 免费（可自己部署）

### 为什么不需要

1. **表情包系统**: 只存储文本描述，不存储图片
2. **内容推荐**: 只存储链接和摘要，不存储文件
3. **对话系统**: 只存储文本，不存储文件

### 如果将来需要

MinIO 是开源的对象存储服务，可以：
- 自己部署（Docker 一键启动）
- 使用云服务商的对象存储（阿里云 OSS、腾讯云 COS 等）
- 完全免费（自己部署）或按量付费（云服务）

---

## 🚀 快速配置步骤

### 1. 检查当前配置

```bash
cd backend
cat .env | grep -E "OPENAI_API_KEY|JWT_SECRET|WEIBO_API_KEY"
```

### 2. 生成 JWT_SECRET

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. 更新 .env 文件

```env
# OpenAI 配置（已正确）
OPENAI_API_KEY=sk-xyuqotucvlvthyssvbnkqxtwhbylgummomshkqvfecaueghcx
OPENAI_API_BASE=https://api.siliconflow.cn/v1
OPENAI_MODEL=deepseek-ai/DeepSeek-V3

# JWT 密钥（需要替换为生成的随机字符串）
JWT_SECRET=nlNLbV62eKjedCT3tOacNEVE13cBRC25I61KtQcTMiw

# 以下配置不需要（可以删除或留空）
# WEIBO_API_KEY=
# MINIO_ENDPOINT=
# MINIO_ACCESS_KEY=
# MINIO_SECRET_KEY=
```

### 4. 重启服务

```bash
docker-compose restart api
docker-compose restart celery-worker
```

---

## 💰 费用总结

| 项目 | 费用 | 说明 |
|------|------|------|
| 硅基流动 API | 按量付费 | 非常便宜，日常使用几乎可忽略 |
| JWT_SECRET | 免费 | 自己生成 |
| RSSHub | 免费 | 开源项目 |
| MinIO | 免费 | 未使用 |
| **总计** | **~¥0-10/月** | 主要是 API 调用费用 |

---

## 🔒 安全建议

### 1. 不要将密钥提交到 Git

在 `.gitignore` 中添加：
```
.env
.env.local
.env.production
```

### 2. 使用环境变量（生产环境）

```bash
# 不要在代码中硬编码
export OPENAI_API_KEY="your-key-here"
export JWT_SECRET="your-secret-here"
```

### 3. 定期轮换密钥

- JWT_SECRET: 每 3-6 个月更换一次
- OPENAI_API_KEY: 如果泄露立即更换

---

## 📚 相关文档

- **RSSHub 文档**: https://docs.rsshub.app/
- **硅基流动文档**: https://docs.siliconflow.cn/
- **MinIO 文档**: https://min.io/docs/

---

## ❓ 常见问题

### Q1: 硅基流动 API 很贵吗？
**A**: 非常便宜！DeepSeek-V3 约 ¥0.0014/1K tokens，日常使用几乎可以忽略不计。

### Q2: 必须使用微博官方 API 吗？
**A**: 不需要！我们使用 RSSHub（完全免费），不需要任何 API Key。

### Q3: JWT_SECRET 可以随便写吗？
**A**: 开发环境可以，但生产环境必须使用强随机字符串。

### Q4: 为什么不需要 MinIO？
**A**: 我们的系统目前只存储文本，不存储图片或文件。

### Q5: RSSHub 会被限流吗？
**A**: 可能会，但我们已经实现了速率限制和缓存机制。

---

**最后更新**: 2026-01-19  
**状态**: ✅ 配置指南完整
