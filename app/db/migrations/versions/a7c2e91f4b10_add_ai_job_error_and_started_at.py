"""add ai job error and started_at

Revision ID: a7c2e91f4b10
Revises: 43312c3613ff
Create Date: 2026-10-01 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c2e91f4b10'
down_revision = '43312c3613ff'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('results', sa.Column('analysis_error', sa.Text(), nullable=True))
    op.add_column('results', sa.Column('roadmap_error', sa.Text(), nullable=True))
    op.add_column('results', sa.Column('analysis_started_at', sa.DateTime(), nullable=True))
    op.add_column('results', sa.Column('roadmap_started_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('results', 'roadmap_started_at')
    op.drop_column('results', 'analysis_started_at')
    op.drop_column('results', 'roadmap_error')
    op.drop_column('results', 'analysis_error')
