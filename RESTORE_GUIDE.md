# 陪伴项目恢复指南 (Restore Guide)

这份文档旨在帮助你在切换 Trae 账号或重新克隆项目后，快速恢复一致的开发环境。

## 1. 克隆项目与初始化

```bash
# 克隆仓库
git clone https://github.com/rhao5556-beep/peiban.git
cd peiban

# 初始化子模块 (Submodules)
# 项目依赖 external/ 目录下的多个外部仓库，必须初始化才能使用
git submodule update --init --recursive
```

## 2. 后端环境恢复 (Backend)

```bash
cd backend

# 1. 恢复环境变量
# 复制示例配置文件
cp .env.example .env

# [重要] 编辑 .env 文件，填入你的真实密钥：
# - OPENAI_API_KEY (硅基流动或其他兼容 API Key)
# - TAVILY_API_KEY (用于联网搜索)
# - WEIBO_API_KEY (如果需要表情包爬取)
# - JWT_SECRET (建议生成一个新的随机字符串)

# 2. 启动基础服务 (Postgres, Redis, Neo4j, Milvus)
docker-compose up -d

# 3. 创建 Python 虚拟环境并安装依赖
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Mac/Linux:
# source venv/bin/activate

pip install -r requirements.txt

# 4. 初始化数据库
python scripts/init_db.py  # 或根据具体情况运行迁移脚本
```

## 3. 前端环境恢复 (Frontend)

```bash
cd ../frontend

# 1. 恢复环境变量
cp .env.example .env

# 2. 安装依赖
npm install

# 3. 启动开发服务器
npm run dev
```

## 4. 验证一致性

1. 访问前端: http://localhost:5173
2. 访问后端 API 文档: http://localhost:8000/docs
3. 检查 external 目录下的子项目是否包含内容。

## 常见问题

- **子模块为空**: 请确保运行了 `git submodule update --init --recursive`。
- **密钥丢失**: `.env` 文件被 git 忽略以保护安全。每次重新克隆都需要手动填入 `API Keys`。
