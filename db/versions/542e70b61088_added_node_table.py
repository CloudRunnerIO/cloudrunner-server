"""Added Node table

Revision ID: 542e70b61088
Revises: 118023293b28
Create Date: 2014-08-28 16:54:23.899491

"""

# revision identifiers, used by Alembic.
revision = '542e70b61088'
down_revision = '118023293b28'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('nodes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('joined_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('key_file', sa.String(length=512), nullable=True),
    sa.Column('cert_file', sa.String(length=512), nullable=True),
    sa.Column('csr_subject', sa.String(length=512), nullable=True),
    sa.Column('org_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['org_id'], [u'organizations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cert_file'),
    sa.UniqueConstraint('key_file'),
    sa.UniqueConstraint('name'),
    sa.UniqueConstraint('name', 'org_id', name='name__org_id')
    )
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('nodes')
    ### end Alembic commands ###
