import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# This must run BEFORE anything imports `app`: backend/src is not on sys.path
# by default, and alembic.ini's `prepend_sys_path = .` only adds backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.config import get_settings  # noqa: E402
from app.models import DB_SCHEMAS, Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# One source of truth for credentials: app.config (env vars, then .env).
config.set_main_option("sqlalchemy.url", get_settings().db.database_url)


def include_name(name: str | None, type_: str, parent_names: dict) -> bool:
    """With include_schemas=True Alembic reflects every schema in the database,
    including PostGIS's `tiger` and `topology`. Without this filter,
    autogenerate would emit DROP TABLE for PostGIS internals."""
    if type_ == "schema":
        return name in DB_SCHEMAS
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_name=include_name,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
