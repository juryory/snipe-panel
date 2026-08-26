"""Alembic 运行环境。

数据库地址不从 alembic.ini 读,而是走 app.config —— 免得同一个配置存两份,
生产上改了 SNIPE_DB_PATH 却忘了改 ini,迁移会跑到错误的库上。
"""
from logging.config import fileConfig

from alembic import context

from app.config import settings
from app.db import Base, engine

# 必须 import 一次 models,SQLAlchemy 才会把表登记到 Base.metadata 上,
# autogenerate 否则会认为所有表都该删掉
from app import models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sqlite_kwargs():
    """SQLite 不支持大多数 ALTER,改列/加约束要靠「建新表-拷数据-换名」。

    render_as_batch 让 Alembic 自动生成这套流程,不加的话 SQLite 上
    几乎任何非「加列」的迁移都会失败。
    """
    return {"render_as_batch": engine.dialect.name == "sqlite"}


def run_migrations_offline() -> None:
    context.configure(
        url=f"sqlite:///{settings.db_path}",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_sqlite_kwargs(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            **_sqlite_kwargs(),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
