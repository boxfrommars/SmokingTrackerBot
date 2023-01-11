"""create smoking table

Revision ID: baf77bafd3ba
Revises: 
Create Date: 2023-01-11 16:18:43.094822

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'baf77bafd3ba'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'smoking',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table('smoking')
