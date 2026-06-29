#!/bin/bash
# ============================================
# V-Stock Radar 一键启动脚本 (Linux / macOS)
# ============================================
set -e

echo "========================================="
echo "  V-Stock Radar - 大V舆情聚合器"
echo "  一键启动脚本"
echo "========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检测 Docker / Docker Compose
if command -v docker-compose &> /dev/null || command -v docker &> /dev/null; then
    echo -e "${GREEN}[✓] 检测到 Docker，使用容器化启动${NC}"
    echo ""

    # 复制 .env 文件
    if [ ! -f .env ]; then
        cp .env.example .env
        echo -e "${YELLOW}[!] 已创建 .env 配置文件${NC}"
    fi

    # 启动所有服务
    if command -v docker-compose &> /dev/null; then
        docker-compose up -d --build
    else
        docker compose up -d --build
    fi

    echo ""
    echo -e "${GREEN}========================================="
    echo "  所有服务已启动！"
    echo "  - 后端 API:  http://localhost:8000"
    echo "  - API 文档:  http://localhost:8000/docs"
    echo "  - 前端页面:  http://localhost:5173"
    echo "=========================================${NC}"
    echo ""
    echo "  查看日志: docker-compose logs -f"
    echo "  停止服务: docker-compose down"
    exit 0
fi

# ===== 本地开发模式 =====
echo -e "${YELLOW}[!] 未检测到 Docker，使用本地开发模式${NC}"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo -e "${RED}[✗] 未检测到 Python，请安装 Python 3.10+${NC}"
    exit 1
fi
PYTHON=$(command -v python3 || command -v python)
echo -e "${GREEN}[✓] Python: $($PYTHON --version)${NC}"

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}[✗] 未检测到 Node.js，请安装 Node.js 18+${NC}"
    exit 1
fi
echo -e "${GREEN}[✓] Node.js: $(node --version)${NC}"

# 检查 Redis
REDIS_PID=""
if command -v redis-server &> /dev/null; then
    echo -e "${GREEN}[✓] 检测到 Redis${NC}"
    # 后台启动 Redis（如果未运行）
    if ! redis-cli ping &> /dev/null 2>&1; then
        redis-server --daemonize yes 2>/dev/null || true
        echo -e "${YELLOW}[!] 已启动 Redis 服务${NC}"
    fi
else
    echo -e "${RED}[✗] 未检测到 Redis，请安装 Redis 或使用 Docker 启动${NC}"
    echo "  安装方法: brew install redis (macOS) / apt install redis (Ubuntu)"
    exit 1
fi

# 创建虚拟环境
if [ ! -d "backend/venv" ]; then
    echo -e "${YELLOW}[!] 创建 Python 虚拟环境...${NC}"
    $PYTHON -m venv backend/venv
fi

# 激活虚拟环境并安装依赖
source backend/venv/bin/activate 2>/dev/null || source backend/venv/Scripts/activate 2>/dev/null
echo -e "${GREEN}[✓] 安装 Python 依赖...${NC}"
pip install -r backend/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple -q

# 启动后端
echo -e "${GREEN}[✓] 启动后端服务 (端口 8000)...${NC}"
cd backend
$PYTHON main.py &
BACKEND_PID=$!
cd ..

# 启动 Celery Worker
echo -e "${GREEN}[✓] 启动 Celery Worker...${NC}"
cd backend
celery -A celery_worker worker --loglevel=info --concurrency=2 &
CELERY_PID=$!
cd ..

# 安装并启动前端
echo -e "${GREEN}[✓] 安装前端依赖...${NC}"
cd frontend
npm install --registry=https://registry.npmmirror.com --silent
echo -e "${GREEN}[✓] 启动前端开发服务器 (端口 5173)...${NC}"
npm run dev -- --host 0.0.0.0 &
FRONTEND_PID=$!
cd ..

echo ""
echo -e "${GREEN}========================================="
echo "  所有服务已启动！"
echo "  - 后端 API:  http://localhost:8000"
echo "  - API 文档:  http://localhost:8000/docs"
echo "  - 前端页面:  http://localhost:5173"
echo "=========================================${NC}"
echo ""
echo "  按 Ctrl+C 停止所有服务"

# 捕获退出信号
trap "echo ''; echo '正在停止服务...'; kill $BACKEND_PID $CELERY_PID $FRONTEND_PID 2>/dev/null; echo '已停止'; exit 0" INT TERM

# 等待
wait
