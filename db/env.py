from __future__ import with_statement
import imp
import os

from alembic import context
from sqlalchemy import engine_from_config, pool
from logging.config import fileConfig

CONF_PATH = os.environ.get('CONFIG_PATH')
if CONF_PATH and os.path.exists(CONF_PATH):
    import sys
    directory, module_name = os.path.split(CONF_PATH)
    mod_name = os.path.splitext(module_name)[0]
    path = list(sys.path)
    sys.path.insert(0, directory)
    try:
        _mod = __import__(mod_name)
        sqla_config = vars(_mod)['sqlalchemy']
    finally:
        sys.path[:] = path  # restore
else:
    from cloudrunner_server.api.config import sqlalchemy as sqla_config

from cloudrunner_server.api.model import *  # noqa

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    #url = config.get_main_option("sqlalchemy.url")
    url = sqla_config['url']
    context.configure(url=url, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    url = sqla_config['url']
    engine = engine_from_config(
        url,
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
        **dict(sqla_config))

    connection = engine.connect()
    context.configure(
        connection=connection,
        target_metadata=target_metadata
    )

    try:
        with context.begin_transaction():
            context.run_migrations()
    finally:
        connection.close()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
