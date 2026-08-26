"""应用配置。所有配置项均可通过环境变量覆盖(前缀 SNIPE_)。"""
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SNIPE_", env_file=".env", extra="ignore")

    # 数据库
    db_path: Path = BASE_DIR / "data" / "snipe.db"

    # 鉴权
    secret_key: str = "dev-only-change-me-in-production"
    token_days: int = 30  # PRD 3.7:登录态保持 30 天
    cookie_name: str = "snipe_token"
    cookie_secure: bool = False  # 生产环境经 HTTPS 暴露时置 True

    # 登录限流(PRD 3.7)
    max_login_failures: int = 5
    lockout_minutes: int = 15
    # 全公司共用一个出口 IP(NAT),这个值不能太紧;账号级锁定才是防爆破的主防线
    login_ip_limit_per_minute: int = 60

    # 扫码查询限流(PRD 3.2:防止按编号规律枚举全量台账)
    by_tag_limit_per_minute: int = 60

    # 事件推送:留空则不推。推给 n8n,由它转发企微/飞书(见 app/webhook.py)
    webhook_url: str = ""
    webhook_token: str = ""  # 非空则以 Authorization: Bearer 发出,供 n8n 校验

    # 库结构:置 0 时退回 create_all(仅测试用,见 app/schema.py)
    run_migrations: bool = True

    # 资产编号
    tag_seq_width: int = 4

    # 初始管理员(仅在用户表为空时创建)
    initial_admin_username: str = "admin"
    initial_admin_password: str = "admin12345"

    # 前端静态文件目录(构建产物)
    static_dir: Optional[Path] = BASE_DIR.parent / "frontend" / "dist"


settings = Settings()
