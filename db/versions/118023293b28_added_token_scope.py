"""Added token scope

Revision ID: 118023293b28
Revises: 348287ebcd3f
Create Date: 2014-08-27 19:08:22.703693

"""

# revision identifiers, used by Alembic.
revision = '118023293b28'
down_revision = '348287ebcd3f'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from cloudrunner_server.api.model import Token
Session = sessionmaker()


def upgrade():
    # commands auto generated by Alembic - please adjust! ###
    op.add_column('tokens', sa.Column(
        'scope', sa.Enum('LOGIN', 'TRIGGER', 'EXECUTE'), nullable=True))
    # end Alembic commands ###
    bind = op.get_bind()
    session = Session(bind=bind)

    def update(token):
        token.scope = 'LOGIN'
    tokens = session.query(Token).all()
    map(update, tokens)
    session.add_all(tokens)
    session.commit()


def downgrade():
    # commands auto generated by Alembic - please adjust! ###
    op.drop_column('tokens', 'scope')
    # end Alembic commands ###
