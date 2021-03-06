"""Added unique for name in Tiers

Revision ID: 2ba9ac1cbd43
Revises: 330568e8928c
Create Date: 2015-02-06 12:05:09.151253

"""

# revision identifiers, used by Alembic.
revision = '2ba9ac1cbd43'
down_revision = '330568e8928c'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_unique_constraint(op.f('uq_usagetiers_name'), 'usagetiers', ['name'])
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(op.f('uq_usagetiers_name'), 'usagetiers', type_='unique')
    ### end Alembic commands ###
