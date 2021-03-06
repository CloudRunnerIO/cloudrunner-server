"""Added CloudProviders

Revision ID: 3176f20feecd
Revises: 2f409626e85b
Create Date: 2015-05-07 14:58:47.922414

"""

# revision identifiers, used by Alembic.
revision = '3176f20feecd'
down_revision = '2f409626e85b'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_unique_constraint(op.f('uq_cloud_profiles_name'), 'cloud_profiles', ['name', 'owner_id'])
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(op.f('uq_cloud_profiles_name'), 'cloud_profiles', type_='unique')
    ### end Alembic commands ###
