"""Cleanup for Batches

Revision ID: 43003fc2f2f4
Revises: 3bfae1b991e3
Create Date: 2015-05-29 12:43:52.455846

"""

# revision identifiers, used by Alembic.
revision = '43003fc2f2f4'
down_revision = '3bfae1b991e3'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('conditions')
    op.drop_table('scriptsteps')
    op.drop_constraint(u'fk_taskgroups_batch_id_batches', 'taskgroups', type_='foreignkey')
    op.drop_table('batches')
    op.drop_column('taskgroups', 'batch_id')
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('taskgroups', sa.Column('batch_id', sa.INTEGER(), autoincrement=False, nullable=True))
    op.create_foreign_key(u'fk_taskgroups_batch_id_batches', 'taskgroups', 'batches', ['batch_id'], ['id'])
    op.create_table('scriptsteps',
    sa.Column('id', sa.INTEGER(), server_default=sa.text(u"nextval('scriptsteps_id_seq'::regclass)"), nullable=False),
    sa.Column('root', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('as_sudo', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('version', sa.VARCHAR(length=40), autoincrement=False, nullable=True),
    sa.Column('batch_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('script_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['batch_id'], [u'batches.id'], name=u'fk_scriptsteps_batch_id_batches'),
    sa.ForeignKeyConstraint(['script_id'], [u'scripts.id'], name=u'fk_scriptsteps_script_id_scripts'),
    sa.PrimaryKeyConstraint('id', name=u'pk_scriptsteps'),
    postgresql_ignore_search_path=False
    )
    op.create_table('conditions',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('type', sa.VARCHAR(length=50), autoincrement=False, nullable=True),
    sa.Column('arguments', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('src_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('dst_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('batch_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['batch_id'], [u'batches.id'], name=u'fk_conditions_batch_id_batches'),
    sa.ForeignKeyConstraint(['dst_id'], [u'scriptsteps.id'], name=u'fk_conditions_dst_id_scriptsteps'),
    sa.ForeignKeyConstraint(['src_id'], [u'scriptsteps.id'], name=u'fk_conditions_src_id_scriptsteps'),
    sa.PrimaryKeyConstraint('id', name=u'pk_conditions')
    )
    op.create_table('batches',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('enabled', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('private', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('source_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['source_id'], [u'scripts.id'], name=u'fk_batches_source_id_scripts'),
    sa.PrimaryKeyConstraint('id', name=u'pk_batches')
    )
    ### end Alembic commands ###