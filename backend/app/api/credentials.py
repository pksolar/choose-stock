"""平台凭据管理 API 路由"""
import logging
from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import PlatformCredential
from app.schemas.schemas import CredentialCreate, CredentialResponse
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/credentials", tags=["凭据管理"])

# Mask password for display
_MASK = "******"


def _mask_credential(cred: PlatformCredential) -> dict:
    return {
        "id": cred.id,
        "platform": cred.platform,
        "username": cred.username,
        "password_masked": _MASK if cred.password else None,
        "is_active": cred.is_active,
        "login_status": cred.login_status,
        "has_cookies": bool(cred.cookies_json),
        "last_login_at": cred.last_login_at.isoformat() if cred.last_login_at else None,
        "created_at": cred.created_at.isoformat() if cred.created_at else None,
        "updated_at": cred.updated_at.isoformat() if cred.updated_at else None,
    }


@router.get("/")
def list_credentials(db: Session = Depends(get_db)):
    """列出所有平台的凭据配置（密码脱敏）"""
    creds = db.query(PlatformCredential).order_by(PlatformCredential.platform).all()
    return [_mask_credential(c) for c in creds]


@router.post("/")
def upsert_credential(data: CredentialCreate, db: Session = Depends(get_db)):
    """创建或更新平台凭据"""
    # Check platform validity
    valid_platforms = {"知乎", "微博", "雪球", "东方财富", "公众号", "同花顺"}
    if data.platform not in valid_platforms:
        raise HTTPException(
            status_code=400,
            detail=f"平台必须是: {', '.join(sorted(valid_platforms))}",
        )

    cred = db.query(PlatformCredential).filter(
        PlatformCredential.platform == data.platform
    ).first()

    if cred:
        cred.username = data.username
        if data.password:
            cred.password = data.password
        cred.login_status = "unknown"
        db.commit()
        db.refresh(cred)
        return {
            "success": True,
            "message": f"已更新 {data.platform} 凭据",
            "credential": _mask_credential(cred),
        }
    else:
        cred = PlatformCredential(
            platform=data.platform,
            username=data.username,
            password=data.password or "",
        )
        db.add(cred)
        db.commit()
        db.refresh(cred)
        return {
            "success": True,
            "message": f"已创建 {data.platform} 凭据",
            "credential": _mask_credential(cred),
        }


@router.get("/{platform}")
def get_credential(platform: str, db: Session = Depends(get_db)):
    """获取指定平台的凭据详情"""
    cred = db.query(PlatformCredential).filter(
        PlatformCredential.platform == platform
    ).first()
    if not cred:
        raise HTTPException(status_code=404, detail=f"未找到 {platform} 的凭据")
    return _mask_credential(cred)


@router.delete("/{platform}")
def delete_credential(platform: str, db: Session = Depends(get_db)):
    """删除平台凭据"""
    cred = db.query(PlatformCredential).filter(
        PlatformCredential.platform == platform
    ).first()
    if not cred:
        raise HTTPException(status_code=404, detail=f"未找到 {platform} 的凭据")
    db.delete(cred)
    db.commit()
    return {"success": True, "message": f"已删除 {platform} 凭据"}


@router.post("/{platform}/login")
async def login_platform(platform: str, db: Session = Depends(get_db)):
    """触发平台登录（使用已存储的凭据）"""
    cred = db.query(PlatformCredential).filter(
        PlatformCredential.platform == platform
    ).first()
    if not cred:
        raise HTTPException(status_code=404, detail=f"未找到 {platform} 的凭据")
    if not cred.username or not cred.password:
        raise HTTPException(
            status_code=400, detail=f"{platform} 凭据不完整，缺少用户名或密码"
        )

    from app.services.browser_manager import browser_manager

    if not browser_manager.is_ready:
        raise HTTPException(status_code=503, detail="浏览器未就绪，请稍后重试")

    login_handlers = {
        "知乎": browser_manager.login_zhihu,
        "微博": browser_manager.login_weibo,
        "雪球": browser_manager.login_xueqiu,
    }

    handler = login_handlers.get(platform)
    if not handler:
        raise HTTPException(
            status_code=400, detail=f"{platform} 暂不支持自动登录"
        )

    success = await handler(cred.username, cred.password)

    cred.login_status = "success" if success else "failed"
    cred.last_login_at = None
    db.commit()

    return {
        "success": success,
        "message": f"{platform} 登录{'成功' if success else '失败，可能需要手动处理验证码'}",
        "login_status": cred.login_status,
    }


@router.post("/{platform}/cookies")
def import_cookies(platform: str, cookies: list = Body(...), db: Session = Depends(get_db)):
    """导入浏览器 Cookie（从 Chrome DevTools 或 EditThisCookie 导出的 JSON 数组）

    Cookie 格式: [{"name": "z_c0", "value": "...", "domain": ".zhihu.com"}, ...]

    导入后 scraper 会直接使用这些 Cookie，无需自动登录。
    """
    import json
    from pathlib import Path
    from config import settings as app_settings

    valid_platforms = {"知乎", "微博", "雪球", "东方财富", "公众号", "同花顺"}
    if platform not in valid_platforms:
        raise HTTPException(
            status_code=400,
            detail=f"平台必须是: {', '.join(sorted(valid_platforms))}",
        )

    if not cookies or not isinstance(cookies, list):
        raise HTTPException(status_code=400, detail="cookies 必须是非空数组")

    # Validate cookie structure
    for c in cookies:
        if "name" not in c or "value" not in c:
            raise HTTPException(
                status_code=400,
                detail="每个 cookie 必须包含 name 和 value 字段",
            )

    # Build Playwright storage state format
    storage_state = {
        "cookies": [],
        "origins": [],
    }

    for c in cookies:
        cookie_entry = {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", ".zhihu.com"),
            "path": c.get("path", "/"),
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", True),
            "sameSite": c.get("sameSite", "Lax"),
        }
        # Handle expiration
        if "expires" in c:
            cookie_entry["expires"] = c["expires"]
        elif "expirationDate" in c:
            cookie_entry["expires"] = c["expirationDate"]

        storage_state["cookies"].append(cookie_entry)

    # Save to auth state file
    auth_dir = Path(app_settings.PLAYWRIGHT_AUTH_DIR)
    auth_dir.mkdir(parents=True, exist_ok=True)
    auth_file = auth_dir / f"{platform}.json"
    auth_file.write_text(
        json.dumps(storage_state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Also store a simplified copy in DB for reference
    cred = db.query(PlatformCredential).filter(
        PlatformCredential.platform == platform
    ).first()
    if not cred:
        cred = PlatformCredential(
            platform=platform,
            username="cookie_import",
            cookies_json=json.dumps(
                {c["name"]: c["value"][:20] + "..." for c in cookies[:10]}
            ),
            login_status="success",
            last_login_at=None,
        )
        db.add(cred)
    else:
        cred.cookies_json = json.dumps(
            {c["name"]: c["value"][:20] + "..." for c in cookies[:10]}
        )
        cred.login_status = "success"

    db.commit()

    cookie_names = [c["name"] for c in cookies]
    return {
        "success": True,
        "message": f"已导入 {len(cookies)} 个 Cookie 到 {platform}",
        "cookie_names": cookie_names,
        "key_cookies": {
            "has_z_c0": "z_c0" in cookie_names,
            "has_d_c0": "d_c0" in cookie_names,
        },
    }
