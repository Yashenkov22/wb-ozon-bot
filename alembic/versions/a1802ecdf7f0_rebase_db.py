"""rebase DB

Revision ID: a1802ecdf7f0
Revises: c1c05f762d59
Create Date: 2025-03-05 20:50:13.329029

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1802ecdf7f0'
down_revision: Union[str, None] = 'c1c05f762d59'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('products',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('product_marker', sa.String(), nullable=True),
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('short_link', sa.String(), nullable=True),
    sa.Column('seller', sa.String(), nullable=True),
    sa.Column('rate', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('short_link')
    )
    op.create_index(op.f('ix_products_id'), 'products', ['id'], unique=False)
    op.create_table('product_prices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.BigInteger(), nullable=True),
    sa.Column('price', sa.Integer(), nullable=True),
    sa.Column('time_price', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('city', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_product_prices_id'), 'product_prices', ['id'], unique=False)
    op.create_table('punkts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('index', sa.BigInteger(), nullable=True),
    sa.Column('city', sa.String(), nullable=True),
    sa.Column('wb_zone', sa.BigInteger(), nullable=True),
    sa.Column('ozon_zone', sa.BigInteger(), nullable=True),
    sa.Column('time_create', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('user_id', sa.BigInteger(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.tg_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_punkts_id'), 'punkts', ['id'], unique=False)
    op.create_table('user_products',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.BigInteger(), nullable=True),
    sa.Column('user_id', sa.BigInteger(), nullable=True),
    sa.Column('link', sa.String(), nullable=True),
    sa.Column('start_price', sa.Integer(), nullable=True),
    sa.Column('actual_price', sa.Integer(), nullable=True),
    sa.Column('sale', sa.Integer(), nullable=True),
    sa.Column('time_create', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.tg_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_products_id'), 'user_products', ['id'], unique=False)
    # add ust_source field to User model
    op.add_column('users', sa.Column('utm_source', sa.String(), nullable=True, default=None))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_user_products_id'), table_name='user_products')
    op.drop_table('user_products')
    op.drop_index(op.f('ix_punkts_id'), table_name='punkts')
    op.drop_table('punkts')
    op.drop_index(op.f('ix_product_prices_id'), table_name='product_prices')
    op.drop_table('product_prices')
    op.drop_index(op.f('ix_products_id'), table_name='products')
    op.drop_table('products')
    # ### end Alembic commands ###
