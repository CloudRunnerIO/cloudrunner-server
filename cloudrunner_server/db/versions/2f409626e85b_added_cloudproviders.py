"""Added CloudProviders

Revision ID: 2f409626e85b
Revises: 231b38dd9bab
Create Date: 2015-05-07 14:51:43.499392

"""

# revision identifiers, used by Alembic.
revision = '2f409626e85b'
down_revision = '231b38dd9bab'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('cloud_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('username', sa.Text(), nullable=True),
    sa.Column('password', sa.Text(), nullable=True),
    sa.Column('arguments', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['owner_id'], [u'users.id'], name=op.f('fk_cloud_profiles_owner_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cloud_profiles'))
    )
    op.create_table('cloud_profiles_shares',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('password', sa.String(length=4000), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('node_quota', sa.Integer(), nullable=True),
    sa.Column('profile_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['profile_id'], [u'cloud_profiles.id'], name=op.f('fk_cloud_profiles_shares_profile_id_cloud_profiles')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cloud_profiles_shares'))
    )
    op.create_table('node_shares',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('share_id', sa.Integer(), nullable=True),
    sa.Column('node_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['node_id'], [u'nodes.id'], name=op.f('fk_node_shares_node_id_nodes')),
    sa.ForeignKeyConstraint(['share_id'], [u'cloud_profiles_shares.id'], name=op.f('fk_node_shares_share_id_cloud_profiles_shares')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_node_shares'))
    )
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('node_shares')
    op.drop_table('cloud_profiles_shares')
    op.drop_table('cloud_profiles')
    ### end Alembic commands ###