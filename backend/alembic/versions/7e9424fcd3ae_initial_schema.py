"""Initial schema

Revision ID: 7e9424fcd3ae
Revises: 
Create Date: 2026-01-27 16:33:13.630190

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7e9424fcd3ae'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users
    op.create_table('users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False, server_default='user'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )

    # Proposals
    op.create_table('proposals',
        sa.Column('proposal_id', sa.Text(), nullable=False),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('base_graph_version', sa.BigInteger(), nullable=False),
        sa.Column('proposal_checksum', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('operations_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('proposal_id')
    )
    op.create_index('idx_proposals_created_at', 'proposals', [sa.text('created_at DESC')], unique=False)
    op.create_index('idx_proposals_tenant_status', 'proposals', ['tenant_id', 'status'], unique=False)

    # AuditLog
    op.create_table('audit_log',
        sa.Column('tx_id', sa.Text(), nullable=False),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('proposal_id', sa.Text(), nullable=False),
        sa.Column('operations_applied', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('revert_operations', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('correlation_id', sa.Text(), server_default='', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('tx_id')
    )
    op.create_index('idx_audit_log_proposal_id', 'audit_log', ['proposal_id'], unique=False)

    # TenantGraphVersion
    op.create_table('tenant_graph_version',
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('graph_version', sa.BigInteger(), server_default='0', nullable=False),
        sa.PrimaryKeyConstraint('tenant_id')
    )

    # GraphChanges
    op.create_table('graph_changes',
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('graph_version', sa.BigInteger(), nullable=False),
        sa.Column('target_id', sa.Text(), nullable=False),
        sa.Column('change_type', sa.Text(), server_default='', nullable=True),
        sa.PrimaryKeyConstraint('tenant_id', 'graph_version', 'target_id')
    )

    # EventsOutbox
    op.create_table('events_outbox',
        sa.Column('event_id', sa.Text(), nullable=False),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('published', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_error', sa.Text(), server_default='', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('event_id')
    )

    # Curricula
    op.create_table('curricula',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('standard', sa.String(length=64), nullable=False),
        sa.Column('language', sa.String(length=2), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )

    # CurriculumNodes
    op.create_table('curriculum_nodes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('curriculum_id', sa.Integer(), nullable=False),
        sa.Column('canonical_uid', sa.String(length=128), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=True),
        sa.Column('is_required', sa.Boolean(), nullable=False, server_default='true'),
        sa.ForeignKeyConstraint(['curriculum_id'], ['curricula.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('curriculum_nodes')
    op.drop_table('curricula')
    op.drop_table('events_outbox')
    op.drop_table('graph_changes')
    op.drop_table('tenant_graph_version')
    op.drop_index('idx_audit_log_proposal_id', table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_index('idx_proposals_tenant_status', table_name='proposals')
    op.drop_index('idx_proposals_created_at', table_name='proposals')
    op.drop_table('proposals')
    op.drop_table('users')
