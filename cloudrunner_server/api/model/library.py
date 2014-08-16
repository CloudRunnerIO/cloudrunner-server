from sqlalchemy.sql.expression import func
from sqlalchemy import (Column, Integer, String, DateTime,
                        Text, ForeignKey, Boolean)
from sqlalchemy.orm import relationship
from .base import TableBase
from .users import User


class Store(TableBase):
    __tablename__ = 'stores'

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    store_type = Column(String(255))


class Script(TableBase):
    __tablename__ = 'scripts'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)
    created_at = Column(DateTime, default=func.now())
    content = Column(Text)
    private = Column(Boolean, default=False)
    mime_type = Column(String(255), default="text/plain")
    store_id = Column(Integer, ForeignKey('stores.id'))
    owner_id = Column(Integer, ForeignKey('users.id'))

    store = relationship(Store)
    owner = relationship(User)
