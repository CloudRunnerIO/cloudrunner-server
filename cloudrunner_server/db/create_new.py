from alembic.config import Config as a_config
from alembic import command, script

from sqlalchemy import create_engine

from cloudrunner import CONFIG_LOCATION
from cloudrunner.util.config import Config
from cloudrunner_server.api.model import Session, metadata

CONFIG = Config(CONFIG_LOCATION)
alembic_cfg = a_config("alembic.ini")


def create_DB():
    engine = create_engine(CONFIG.db)

    Session.bind = engine
    metadata.bind = Session.bind

    metadata.create_all(Session.bind)

    scr_dir = script.ScriptDirectory('.')
    heads = scr_dir.get_heads()
    print "Setting HEAD as %s" % heads[0]
    command.stamp(alembic_cfg, heads[0])

if __name__ == '__main__':
    create_DB()
