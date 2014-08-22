from sqlalchemy.sql.expression import func
from sqlalchemy import (Column, Integer, String, DateTime, Boolean, Text,
                        ForeignKey, UniqueConstraint,
                        or_)
from sqlalchemy.orm import relationship, backref
from .base import TableBase
from .users import User, Org


class Library(TableBase):
    __tablename__ = 'libraries'
    __table_args__ = (
        UniqueConstraint("name", 'org_id'),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    is_link = Column(Boolean)
    owner_id = Column(Integer, ForeignKey(User.id))
    private = Column(Boolean, default=False)
    org_id = Column(Integer, ForeignKey(Org.id))

    org = relationship(Org)
    owner = relationship(User)

    @staticmethod
    def visible(ctx):
        return ctx.db.query(Library).join(User, Org).filter(
            Org.name == ctx.user.org,
            or_(Library.owner_id == ctx.user.id,
                Library.private != True)
        )


class LibraryCreds(TableBase):
    __tablename__ = 'library_creds'

    id = Column(Integer, primary_key=True)
    provider = Column(String(500))
    link = Column(String(500))
    auth_user = Column(String(500))
    auth_pass = Column(String(500))
    auth_args = Column(String(500))
    library_id = Column(Integer, ForeignKey(Library.id))

    library = relationship(Library)


class Folder(TableBase):
    __tablename__ = 'folders'

    __table_args__ = (
        UniqueConstraint("name", "parent_id"),
        UniqueConstraint("full_name", 'library_id'),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    full_name = Column(String(500))
    parent_id = Column(Integer, ForeignKey('folders.id'))
    library_id = Column(Integer, ForeignKey(Library.id))
    owner_id = Column(Integer, ForeignKey(User.id))

    owner = relationship(User)
    parent = relationship('Folder',
                          remote_side=[id],
                          backref=backref('subfolders'))
    scripts = relationship('Script')
    library = relationship(Library, backref=backref('folders'))

    @staticmethod
    def visible(ctx, library, parent=None):
        q = ctx.db.query(Folder).join(
            Library, User, Org).filter(
                Org.name == ctx.user.org,
                Library.name == library,
                or_(Library.owner_id == ctx.user.id,
                    Library.private != True)
            )
        q = q.join(Folder.parent,
                   aliased=True).filter(Folder.full_name == parent)
        return q

    @staticmethod
    def editable(ctx, library, folder_path):
        q = ctx.db.query(Folder).join(
            Library, User, Org).filter(
                Folder.full_name == folder_path,
                Org.name == ctx.user.org,
                Library.name == library,
                or_(Library.owner_id == ctx.user.id,
                    Library.private != True)
            )
        return q


class Script(TableBase):
    __tablename__ = 'scripts'
    __table_args__ = (
        UniqueConstraint("name", "folder_id"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    folder_id = Column(Integer, ForeignKey(Folder.id))
    created_at = Column(DateTime, default=func.now())
    content = Column(Text)
    mime_type = Column(String(255), default="text/plain")
    owner_id = Column(Integer, ForeignKey(User.id))

    folder = relationship(Folder)
    owner = relationship(User)

    @staticmethod
    def visible(ctx, library, folder):
        q = ctx.db.query(Script).join(
            Folder, Library, User, Org).filter(
                Org.name == ctx.user.org,
                Library.name == library,
                or_(Library.owner_id == ctx.user.id,
                    Library.private != True),
                Folder.full_name == folder
            )
        return q

    @staticmethod
    def find(ctx, path):
        library, _, path = path.partition("/")
        folder, _, script = path.rpartition("/")

        folder = "/" + folder + "/"
        q = Script.visible(ctx, library, folder).filter(Script.name == script)

        return q
