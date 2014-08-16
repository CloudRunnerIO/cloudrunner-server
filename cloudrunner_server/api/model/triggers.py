from cloudrunner.util import Enum
from sqlalchemy.sql.expression import func
from sqlalchemy import Column, Boolean, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship, backref

from .base import TableBase
from .users import User
from .library import Script


SOURCE_TYPE = Enum('N/A', 'CRON', 'ENV', 'LOG_CONTENT', 'EXTERNAL')


class Job(TableBase):
    __tablename__ = 'jobs'

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=func.now())
    name = Column(String(256), index=True, unique=True)
    enabled = Column(Boolean)
    source = Column(Integer)
    arguments = Column(String(1000))

    target_id = Column(Integer, ForeignKey('scripts.id'))
    owner_id = Column(Integer, ForeignKey('users.id'))

    target = relationship(Script)
    owner = relationship(User)
