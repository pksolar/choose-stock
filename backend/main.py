"""
V-Stock Radar (大V舆情聚合器) - FastAPI 主应用入口
"""
import sys
import asyncio
from pathlib import Path

# Windows: ProactorEventLoop is required for subprocess support (Playwright/Chromium)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# 确保 backend 目录在 Python path 中
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import settings
from app.models.database import init_db
from app.models.models import VStar, Article
from app.models.database import SessionLocal
from app.services.scraper import generate_mock_articles
from app.utils.stock_mapper import stock_mapper

from app.api.vstars import router as vstars_router
from app.api.analysis import router as analysis_router
from app.api.stocks import router as stocks_router
from app.api.credentials import router as credentials_router


def seed_initial_data():
    """初始化种子数据：添加示例大V，并触发后台文章抓取。"""
    db = SessionLocal()
    try:
        # 示例大V（真实知乎用户）
        BUILTIN_VSTARS = [
            ("张佳玮", "知乎", "auto", 1.0),
        ]

        for nickname, platform, mode, weight in BUILTIN_VSTARS:
            existing = db.query(VStar).filter(VStar.nickname == nickname).first()
            if not existing:
                vstar = VStar(
                    nickname=nickname,
                    platform=platform,
                    data_source_mode=mode,
                    weight_coefficient=weight,
                )
                db.add(vstar)
                print(f"  已添加示例大V: {nickname} ({platform})")

        db.commit()

        if settings.USE_MOCK_DATA:
            vstars = db.query(VStar).all()
            articles = generate_mock_articles(db, vstars)
            print(f"已生成 {len(articles)} 篇模拟文章")
        else:
            import threading
            from app.services.scraper import scrape_and_persist

            def _scrape_all_vstars():
                db2 = SessionLocal()
                try:
                    vstars = db2.query(VStar).all()
                    for vstar in vstars:
                        try:
                            count = scrape_and_persist(vstar, db2)
                            if count > 0:
                                print(f"  已为 '{vstar.nickname}' 抓取 {count} 篇文章")
                            else:
                                print(f"  '{vstar.nickname}' 暂未抓取到文章（请检查昵称或使用刷新按钮重试）")
                        except Exception as e:
                            print(f"  抓取 '{vstar.nickname}' 失败: {e}")
                finally:
                    db2.close()

            threading.Thread(target=_scrape_all_vstars, daemon=True).start()
            print("已启动后台文章抓取任务...")

    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    print(f"启动 {settings.APP_NAME} v{settings.APP_VERSION}")
    init_db()
    print("数据库表已初始化")
    stock_mapper.load_from_akshare()  # 尝试加载全量股票列表
    print(f"股票映射已加载，共 {stock_mapper.stock_count} 只股票")

    # 启动 Playwright 浏览器
    try:
        from app.services.browser_manager import browser_manager
        await browser_manager.start()
    except Exception as e:
        print(f"[WARN] 浏览器启动失败: {e}，爬虫将使用 Mock 数据")

    seed_initial_data()
    yield
    # 关闭时执行
    try:
        from app.services.browser_manager import browser_manager
        await browser_manager.stop()
    except Exception:
        pass
    print("应用关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="大V舆情聚合器 - 自动发现多位大V共同看多的A股股票",
    lifespan=lifespan,
)

# CORS 配置（允许前端开发服务器）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{settings.FRONTEND_PORT}",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(vstars_router)
app.include_router(analysis_router)
app.include_router(stocks_router)
app.include_router(credentials_router)


@app.get("/")
def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }


@app.get("/api/health")
def health_check():
    return {"status": "ok", "mock_data": settings.USE_MOCK_DATA}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.BACKEND_PORT,
        reload=settings.DEBUG,
    )
