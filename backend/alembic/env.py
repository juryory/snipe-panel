"""Alembic 运行环境。

数据库地址不从 alembic.ini 读,而是走 app.config —— 免得同一个配置存两份,
生产上改了 SNIPE_DB_PATH 却忘了改 ini,迁移会跑到错误的库上。
"""
from logging.config import fileConfig

from alembic import context

from sqlalchemy import create_engine, event, text

from app.config import settings
from app.db import Base

# 必须 import 一次 models,SQLAlchemy 才会把表登记到 Base.metadata 上,
# autogenerate 否则会认为所有表都该删掉
from app import models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _migration_engine():
    """迁移专用连接。

    不复用 app.db.engine:那个引擎给每条连接都开了 PRAGMA foreign_keys=ON,
    而 SQLite 的 batch 迁移靠「建新表-拷数据-DROP 旧表-改名」实现 ——
    只要子表里有行引用着被重建的表,DROP 那一步就会被外键挡住,整个迁移回滚。
    (实际踩过:删 assets.barcode 时被 checkout_records 挡住,容器起不来。)

    必须在连接建立时就关掉:PRAGMA foreign_keys 在事务内部是空操作,写在
    迁移脚本里不起作用。迁移跑完会用 foreign_key_check 复核完整性。
    """
    migration_engine = create_engine(f"sqlite:///{settings.db_path}", future=True)

    @event.listens_for(migration_engine, "connect")
    def _pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=OFF")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    return migration_engine


def _sqlite_kwargs(dialect_name: str):
    """SQLite 不支持大多数 ALTER,改列/加约束要靠「建新表-拷数据-换名」。

    render_as_batch 让 Alembic 自动生成这套流程,不加的话 SQLite 上
    几乎任何非「加列」的迁移都会失败。
    """
    return {"render_as_batch": dialect_name == "sqlite"}


def run_migrations_offline() -> None:
    context.configure(
        url=f"sqlite:///{settings.db_path}",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_sqlite_kwargs("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    migration_engine = _migration_engine()
    try:
        with migration_engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                **_sqlite_kwargs(connection.dialect.name),
            )
            with context.begin_transaction():
                context.run_migrations()

            # 迁移期间外键是关掉的,跑完必须复核 —— 万一某个迁移真把引用弄坏了,
            # 宁可在这里炸掉,也不要留一个悄悄损坏的库继续用下去
            broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if broken:
                raise RuntimeError(f"迁移后外键完整性受损:{broken[:10]}")
    finally:
        migration_engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
