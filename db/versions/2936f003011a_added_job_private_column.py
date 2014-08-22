"""Added Job private column

Revision ID: 2936f003011a
Revises: 55d3e12cab31
Create Date: 2014-08-19 15:47:48.505316

"""

# revision identifiers, used by Alembic.
revision = '2936f003011a'
down_revision = '55d3e12cab31'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('jobs', sa.Column('private', sa.Boolean(), nullable=True))
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('jobs', 'private')
    ### end Alembic commands ###
