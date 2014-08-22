from sqlalchemy.sql.expression import func
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship, backref
from .base import TableBase
from .users import User


class LOG_STATUS(object):
    Unknown = None
    Running = 1
    Finished = 2

    @staticmethod
    def from_value(val):
        if val == 1:
            return 'Running'
        elif val == 2:
            return 'Finished'
        else:
            return 'Unknown'


class Log(TableBase):
    __tablename__ = 'logs'

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=func.now())
    uuid = Column(String(40), index=True, unique=True)
    exit_code = Column(Integer)
    timeout = Column(Integer)
    status = Column(Integer)
    source_type = Column(Integer)
    source = Column(String(1000))

    owner_id = Column(Integer, ForeignKey('users.id'))

    owner = relationship(User)


class Step(TableBase):
    __tablename__ = 'steps'

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=func.now())
    target = Column(Text)
    timeout = Column(Integer)
    lang = Column(String(100))
    script = Column(Text)
    env_in = Column(Text)
    env_out = Column(Text)

    log_id = Column(Integer, ForeignKey('logs.id'))

    log = relationship('Log', backref=backref('steps'))


class Tag(TableBase):
    __tablename__ = 'tags'

    id = Column(Integer, primary_key=True)
    name = Column(String(100))

    log_id = Column(Integer, ForeignKey('logs.id'))

    log = relationship(Log, backref=backref('tags'))
