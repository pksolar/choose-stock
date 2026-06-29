# V-Stock Radar (大V舆情聚合器)

> 自动发现多位大V在同一时间段内，以看多态度共同提及的A股股票

## 核心功能

- **大V管理**：支持公众号/知乎/雪球/微博/东方财富/同花顺等平台，可配置权重系数和数据源模式
- **智能分析**：NLP 自动识别文章中提及的A股股票，分析情感倾向（看多/中性/看空）
- **交叉比对**：自动发现被多位大V共同看多的股票，按热度值排序展示
- **证据链**：点击股票查看每位大V的原文摘要、情感标签、原文链接
- **K线图**：叠加显示股票近期K线走势，绿色虚线标注大V集中提及时间点
- **异步处理**：Celery 后台处理爬取和分析任务，前端轮询实时更新进度

## 快速开始

### 方式一：Docker 一键启动（推荐）

```bash
# 1. 克隆或进入项目目录
cd vstock-radar

# 2. 启动所有服务（需要 Docker 和 docker-compose）
docker compose up -d --build

# 3. 访问服务
# 前端: http://localhost:5173
# 后端API: http://localhost:8000
# API文档: http://localhost:8000/docs
```

### 方式二：本地开发模式

**前置要求**：
- Python 3.10+
- Node.js 18+
- Redis（运行在 localhost:6379）

```bash
# Linux/Mac
chmod +x start.sh
./start.sh

# Windows
start.bat
```

### 方式三：手动启动

```bash
# 1. 启动 Redis
redis-server

# 2. 安装并启动后端
cd backend
pip install -r requirements.txt
python main.py

# 3. 启动 Celery Worker（新终端）
cd backend
celery -A celery_worker worker --loglevel=info --concurrency=2 --pool=solo

# 4. 安装并启动前端（新终端）
cd frontend
npm install
npm run dev
```

## 使用流程

1. **配置大V**：进入「大V管理」页面，系统已内置10位示例大V和模拟文章数据
2. **开始分析**：在首页选择时间窗口（3天/1周/1个月），设置最低提及人数，点击「开始分析」
3. **查看榜单**：分析完成后，页面自动展示热度榜单，按热度值降序排列
4. **查看详情**：点击任意股票行，弹出证据链弹窗：
   - 左侧：K线图（可切换1月/3月），绿色虚线标注集中提及时间
   - 右侧：证据链列表，包含每位大V的原文摘要、情感标签、发布时间

## 配置说明

编辑 `.env` 文件（从 `.env.example` 复制）：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `USE_MOCK_DATA` | 是否使用模拟数据（演示模式） | `true` |
| `DATABASE_URL` | 数据库连接 | SQLite |
| `REDIS_URL` | Redis 地址 | `localhost:6379` |
| `SCRAPER_DELAY_MIN/MAX` | 爬虫请求间隔（秒） | 2.0 / 5.0 |
| `BACKEND_PORT` | 后端端口 | 8000 |
| `FRONTEND_PORT` | 前端端口 | 5173 |

设置 `USE_MOCK_DATA=false` 后，系统会尝试真实抓取（需配置 Playwright 和代理）。

## 热度算法

```
热度值 = (提及人数 × 平均权重系数) + (总提及次数 × 0.5)
```

- **提及人数**：有多少位不同大V提及了该股票
- **权重系数**：每位大V可单独配置（默认：雪球 1.0，知乎 0.8，其他 0.6）
- **去重规则**：同一大V对同一股票在一个时间窗口内只计1次有效提及

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI (Python) |
| 异步任务 | Celery + Redis |
| 数据库 | SQLite (可切换 PostgreSQL) |
| NLP | SnowNLP + jieba + 自定义金融词典 |
| K线数据 | akshare |
| 前端 | Vue 3 + Element Plus |
| 图表 | ECharts |
| 部署 | Docker / docker-compose |

## API 接口概览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/vstars/` | 获取大V列表 |
| POST | `/api/vstars/` | 添加大V |
| PUT | `/api/vstars/{id}` | 更新大V |
| DELETE | `/api/vstars/{id}` | 删除大V |
| POST | `/api/analysis/start` | 启动分析任务 |
| GET | `/api/analysis/task/{id}` | 查询任务状态 |
| GET | `/api/analysis/results/{id}` | 获取分析结果 |
| GET | `/api/analysis/stock-detail/{id}/{code}` | 个股证据链 |
| GET | `/api/stocks/kline/{code}` | 获取K线数据 |
| GET | `/api/stocks/search?q=` | 搜索股票 |

详细文档访问：http://localhost:8000/docs (Swagger UI)

## 项目结构

```
/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI 路由
│   │   ├── celery_tasks/  # Celery 异步任务
│   │   ├── models/        # SQLAlchemy ORM 模型
│   │   ├── schemas/       # Pydantic 校验模型
│   │   ├── services/      # 业务逻辑（爬虫/NLP/分析/K线）
│   │   └── utils/         # 工具类（股票映射等）
│   ├── config.py           # 全局配置
│   ├── main.py             # FastAPI 入口
│   ├── celery_worker.py    # Celery Worker 入口
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/            # Axios API 封装
│   │   ├── components/     # 公共组件（K线图/证据链）
│   │   ├── views/          # 页面（看板/大V管理）
│   │   ├── router/         # Vue Router
│   │   └── store/          # Pinia 状态管理
│   ├── package.json
│   └── vite.config.js
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
├── start.sh / start.bat
└── README.md
```

## 免责声明

**本系统仅汇总网络公开言论，所有数据仅供参考，不构成任何投资建议。股票投资有风险，入市需谨慎。系统分析结果基于公开文章的 NLP 自动处理，可能存在误判，请用户自行判断。**

## License

MIT
