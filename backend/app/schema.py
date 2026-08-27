"""库结构管理。

用 Alembic 迁移代替 create_all。create_all 只会建缺失的表,**不会给已存在的表
加列** —— 一旦线上录了真实数据,再改模型就只能手写 ALTER 或者删库重来。
"""
import logging
import sys

from sqlalchemy import inspect

from .config import BASE_DIR, settings
from .db import Base, engine

logger = logging.getLogger("snipe")


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    # 用绝对路径:容器里工作目录和本地不一样,相对路径会找不到 versions/
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    return cfg


def ensure_schema() -> None:
    """把库结构升到最新版本。

    三种情况都要照顾到:

    - **全新库** —— 从头跑全部迁移
    - **历史遗留库**(接 Alembic 之前用 create_all 建的,没有 alembic_version 表)
      —— 先打上基线标记再升级。不打标记的话 upgrade 会从头执行建表,撞上
      「表已存在」直接失败
    - **已在迁移管理下** —— 只补跑缺的那几个

    测试里走 create_all(SNIPE_RUN_MIGRATIONS=0):每个用例都重建库,跑迁移
    纯属浪费。迁移本身由 tests/test_migrations.py 单独验证。
    """
    if not settings.run_migrations:
        Base.metadata.create_all(engine)
        return

    from alembic import command
    from alembic.script import ScriptDirectory

    cfg = _alembic_config()
    tables = set(inspect(engine).get_table_names())

    if tables and "alembic_version" not in tables:
        base = ScriptDirectory.from_config(cfg).get_base()
        logger.warning("检测到未纳入迁移管理的旧库,按基线 %s 标记后再升级", base)
        command.stamp(cfg, base)

    try:
        command.upgrade(cfg, "head")
    except Exception:
        # 直接往 stderr 打一份。alembic 加载 env.py 时会重配 logging,
        # 异常靠 logger 往上抛有被吞掉的风险,而迁移失败是必须让人看见的事 ——
        # 看不见的话表现就是容器不停重启、日志里却只有 INFO。
        import traceback

        print("=" * 60, file=sys.stderr)
        print("数据库迁移失败,应用无法启动:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.stderr.flush()
        raise
