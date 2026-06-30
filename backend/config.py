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

    # 服务端口
    BACKEND_PORT: int = 8000
    FRONTEND_PORT: int = 5173

    # Playwright 浏览器自动化
    PLAYWRIGHT_HEADLESS: bool = True
    PLAYWRIGHT_TIMEOUT: int = 30000  # 页面加载超时（毫秒）

    # 平台凭据持久化
    PLAYWRIGHT_AUTH_DIR: str = str(BASE_DIR / "data" / "auth_states")

    # 默认平台凭据（可在 .env 中配置，也可通过 API/UI 配置）
    ZHIHU_USERNAME: str = ""
    ZHIHU_PASSWORD: str = ""
    WEIBO_USERNAME: str = ""
    WEIBO_PASSWORD: str = ""
    XUEQIU_USERNAME: str = ""
    XUEQIU_PASSWORD: str = ""

    class Config:
        env_file = str(BASE_DIR / ".." / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"  # 忽略 .env 中多余的字段（如旧版 Redis 配置）


settings = Settings()

# 确保数据目录存在
os.makedirs(BASE_DIR / "data", exist_ok=True)
os.makedirs(BASE_DIR / "data" / "auth_states", exist_ok=True)
