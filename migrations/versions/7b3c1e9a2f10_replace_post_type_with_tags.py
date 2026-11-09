"""replace post content_type with tags

Revision ID: 7b3c1e9a2f10
Revises: 5e9f8760c4cc
Create Date: 2026-11-08 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7b3c1e9a2f10'
down_revision: Union[str, Sequence[str], None] = '5e9f8760c4cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('tags',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('name', sa.VARCHAR(length=30), nullable=False),
    sa.Column('post_count', sa.INTEGER(), server_default='0', nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tags_name'), 'tags', ['name'], unique=True)
    op.create_index(op.f('ix_tags_post_count'), 'tags', ['post_count'], unique=False)
    op.create_table('post_tags',
    sa.Column('post_id', sa.UUID(), nullable=False),
    sa.Column('tag_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['post_id'], ['posts.id'], ),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ),
    sa.PrimaryKeyConstraint('post_id', 'tag_id')
    )
    op.create_index(op.f('ix_post_tags_tag_id'), 'post_tags', ['tag_id'], unique=False)

    if _has_column('posts', 'content_type'):
        # recipe/tip become tags; "other" carries no meaning so it is dropped
        op.execute("""
            INSERT INTO tags (name)
            SELECT DISTINCT lower(content_type::text) FROM posts
            WHERE lower(content_type::text) IN ('recipe', 'tip')
        """)
        op.execute("""
            INSERT INTO post_tags (post_id, tag_id)
            SELECT p.id, t.id FROM posts p JOIN tags t ON t.name = lower(p.content_type::text)
        """)
        op.execute("UPDATE tags SET post_count = (SELECT count(*) FROM post_tags pt WHERE pt.tag_id = tags.id)")
        op.drop_column('posts', 'content_type')
    op.execute("DROP TYPE IF EXISTS post_type")


def downgrade() -> None:
    """Downgrade schema."""
    post_type = postgresql.ENUM('RECIPE', 'TIP', 'OTHER', name='post_type')
    post_type.create(op.get_bind(), checkfirst=True)
    op.add_column('posts', sa.Column('content_type', post_type, nullable=True))
    op.execute("UPDATE posts SET content_type = 'OTHER'")
    for tag, value in (('tip', 'TIP'), ('recipe', 'RECIPE')):
        op.execute(f"""
            UPDATE posts p SET content_type = '{value}'
            FROM post_tags pt JOIN tags t ON t.id = pt.tag_id
            WHERE pt.post_id = p.id AND t.name = '{tag}'
        """)
    op.alter_column('posts', 'content_type', nullable=False)
    op.create_index(op.f('ix_posts_content_type'), 'posts', ['content_type'], unique=False)

    op.drop_index(op.f('ix_post_tags_tag_id'), table_name='post_tags')
    op.drop_table('post_tags')
    op.drop_index(op.f('ix_tags_post_count'), table_name='tags')
    op.drop_index(op.f('ix_tags_name'), table_name='tags')
    op.drop_table('tags')
