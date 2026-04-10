"""
Alembic migration environment configuration.

This file is the bridge between Alembic (the database migration tool) and
the application's SQLAlchemy models. Alembic runs this file when you run
any migration command such as "alembic upgrade head".

Its two main jobs are:
  1. Connect Alembic to the database using the same DATABASE_URL that
     the application uses, loaded from the .env file.
  2. Import all the application's models so Alembic knows what the target
     schema should look like when generating new migrations.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from dotenv import find_dotenv, load_dotenv
from sqlalchemy import engine_from_config, pool

# Add the api/ directory to the Python path so that imports like
# "from database import Base" work when Alembic is run from any directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Load environment variables from the .env file at the project root.
# find_dotenv() searches parent directories so this works regardless of
# which directory the command is run from.
load_dotenv(find_dotenv())

# Import the Base class (which tracks all models) and all model modules.
# The models import is not used directly but importing it registers all
# three tables (sets, cards, price_snapshots) on Base.metadata, which
# Alembic needs to detect schema changes for autogenerate.
from database import Base  # noqa: E402
import models  # noqa: E402, F401

# Read the Alembic configuration object, which comes from alembic.ini.
config = context.config

# Configure Python's standard logging using the settings in alembic.ini
# so that Alembic's output appears in the console during migrations.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the database URL in the Alembic config with the value from the
# environment. This means the URL in alembic.ini is intentionally left
# blank -- the real value always comes from the .env file.
config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

# Tell Alembic what the schema should look like by pointing it at the
# metadata object that holds all the model definitions.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in offline mode.

    Offline mode generates SQL statements without connecting to the database.
    This is useful for previewing what a migration will do or for applying
    migrations in environments where a direct database connection is not
    available. The SQL is written to stdout instead of being executed.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in online mode (the normal case).

    Online mode connects to the database and executes the migration SQL
    directly. This is what happens when the API server starts up and
    calls "alembic upgrade head".
    """
    # Create a database connection using the URL from the config.
    # NullPool means connections are not reused after the migration
    # finishes, which is the correct behavior for a one-shot script.
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


# Determine which mode to run in and call the appropriate function.
# Alembic sets the offline flag when you pass "--sql" to the command line.
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
