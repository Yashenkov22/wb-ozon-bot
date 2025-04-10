"""Add last_send_price field to UserProduct DB model

Revision ID: 38640b2649ff
Revises: e5c5202a2b6f
Create Date: 2025-04-09 10:13:09.239820

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '38640b2649ff'
down_revision: Union[str, None] = 'e5c5202a2b6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('user_products', sa.Column('last_send_price', sa.Integer(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('user_products', 'last_send_price')
    # ### end Alembic commands ###
