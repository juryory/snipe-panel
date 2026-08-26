"""应用入口。

PRD 第 7 节:前端构建产物由本服务同域托管 —— 无 CORS,SameSite=Lax Cookie 即可防 CSRF。
"""
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .config import settings
from .db import Base, SessionLocal, engine
from .models import Category, Role, User
from .routers import assets, auth, categories, checkouts, companies, inventory, users
from .security import hash_password

logger = logging.getLogger("snipe")

DEFAULT_CATEGORIES = [
    ("电脑", "PC"),
    ("相机", "CAM"),
    ("镜头", "LENS"),
    ("直播设备", "LIVE"),
    ("外设", "ACC"),
]


def bootstrap() -> None:
    """建表 + 首次运行时写入初始管理员与默认分类。"""
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        has_user = db.execute(select(User.id).limit(1)).first()
        if not has_user:
            admin = User(
                username=settings.initial_admin_username,
                password_hash=hash_password(settings.initial_admin_password),
                real_name="系统管理员",
                role=Role.ADMIN,
                must_change_password=True,  # PRD 3.7:首次登录强制改密
            )
            db.add(admin)
            logger.warning(
                "已创建初始管理员 %s,初始密码见配置,首次登录必须修改",
                settings.initial_admin_username,
            )
        has_category = db.execute(select(Category.id).limit(1)).first()
        if not has_category:
            for name, prefix in DEFAULT_CATEGORIES:
                db.add(Category(name=name, tag_prefix=prefix))
        db.commit()


app = FastAPI(
    title="设备资产管理系统",
    description="公司内部设备台账 · 扫码借还",
    version="0.1.0",
)

app.include_router(auth.router)
app.include_router(assets.router)
app.include_router(categories.router)
app.include_router(companies.router)
app.include_router(checkouts.router)
app.include_router(inventory.router)
app.include_router(users.router)


@app.on_event("startup")
def on_startup() -> None:
    bootstrap()


@app.get("/api/health")
def health():
    return {"ok": True}


# ---------- 前端静态文件 ----------
_dist: Path = settings.static_dir if settings.static_dir else None

if _dist and (_dist / "index.html").exists():
    if (_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str, request: Request):
        """SPA 路由回退。

        /api/* 已由上面的路由处理;能走到这里说明是前端路由或静态文件。
        """
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "接口不存在"}, status_code=404)
        candidate = (_dist / full_path).resolve()
        # 防目录穿越:请求路径必须落在 dist 目录内
        if full_path and candidate.is_file() and _dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def no_frontend():
        return JSONResponse(
            {
                "detail": "前端尚未构建。请在 frontend/ 下执行 npm install && npm run build,"
                "或开发时用 npm run dev(Vite 会把 /api 代理到本服务)。"
            }
        )
