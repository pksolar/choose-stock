"""
全局配置模块
使用 pydantic-settings 从 .env 文件和环境变量加载配置
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    # 应用基础配置
    APP_NAME: str = "V-Stock Radar"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # 数据库配置（默认使用 SQLite）
    DATABASE_URL_SYNC: str = f"sqlite:///{BASE_DIR}/data/vstock.db"

    # Redis 配置（Celery broker + result backend）
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery 配置
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # 爬虫配置
    SCRAPER_DELAY_MIN: float = 2.0   # 最小请求间隔（秒）
    SCRAPER_DELAY_MAX: float = 5.0   # 最大请求间隔（秒）
    SCRAPER_USER_AGENT_POOL: list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    ]
    USE_MOCK_DATA: bool = False  # 默认使用真实数据抓取

    # NLP 缓存时间（秒）
    NLP_CACHE_TTL: int = 3600

    # CSRF 保护开关
    CSRF_ENABLED: bool = False

    # 服务端口
    BACKEND_PORT: int = 8000
    FRONTEND_PORT: int = 5173

    # Playwright 浏览器自动化
    PLAYWRIGHT_HEADLESS: bool = True
    PLAYWRIGHT_TIMEOUT: int = 30000  # 页面加载超时（毫秒）
    BROWSER_USE_CDP: bool = False   # 连接已有 Chrome 而非启动新浏览器
    BROWSER_CDP_ENDPOINT: str = "http://localhost:9222"

    class Config:
        env_file = str(BASE_DIR / ".." / ".env")
        env_file_encoding = "utf-8"


settings = Settings()

# 确保数据目录存在
os.makedirs(BASE_DIR / "data", exist_ok=True)


def check_redis_available() -> bool:
    """检测 Redis 是否可用"""
    try:
        import redis
        r = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
        r.close()
        return True
    except Exception:
        return False


REDIS_AVAILABLE = check_redis_available()

if not REDIS_AVAILABLE:
    print("[WARN] Redis 不可用，将使用同步模式运行（不需要 Celery Worker）")
    print("       如需异步处理，请安装并启动 Redis，然后重启后端")

