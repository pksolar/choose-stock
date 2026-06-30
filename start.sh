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

# 创建 .env 文件
if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${YELLOW}[!] 已创建 .env 配置文件${NC}"
fi

# 安装 Python 依赖
echo -e "${GREEN}[✓] 安装 Python 依赖...${NC}"
pip install -r backend/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple -q

# 启动后端
echo -e "${GREEN}[✓] 启动后端服务 (端口 8000)...${NC}"
cd backend
$PYTHON main.py &
BACKEND_PID=$!
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
trap "echo ''; echo '正在停止服务...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo '已停止'; exit 0" INT TERM

# 等待
wait
