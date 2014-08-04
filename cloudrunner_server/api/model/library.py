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


class Workflow(TableBase):
    __tablename__ = 'workflows'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)
    created_at = Column(DateTime, default=func.now())
    content = Column(Text)
    private = Column(Boolean, default=False)

    store_id = Column(Integer, ForeignKey('stores.id'))
    owner_id = Column(Integer, ForeignKey('users.id'))

    store = relationship(Store)
    owner = relationship(User)


class Inline(TableBase):
    __tablename__ = 'inlines'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)
    created_at = Column(DateTime, default=func.now())
    lang = Column(String(100), default='bash')
    content = Column(Text)
    private = Column(Boolean, default=False)

    owner_id = Column(Integer, ForeignKey('users.id'))

    owner = relationship(User)
