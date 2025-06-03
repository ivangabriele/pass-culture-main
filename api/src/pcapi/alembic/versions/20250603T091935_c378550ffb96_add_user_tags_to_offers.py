"""Add "offer_tag_mapping" table."""

import sqlalchemy as sa
from alembic import op


# pre/post deployment: pre
# revision identifiers, used by Alembic.
revision = "c378550ffb96"
down_revision = "ba09ac03eb93"
branch_labels: tuple[str] | None = None
depends_on: list[str] | None = None


def upgrade() -> None:
    op.create_table(
        "offer_tag_mapping",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("offerId", sa.BigInteger(), nullable=False),
        sa.Column("tagId", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["tagId"], ["user_tag.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offerId"], ["offer.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offerId", "tagId", name="unique_offer_tag_mapping"),
    )
    op.create_index(op.f("ix_offer_tag_mapping_tagId"), "offer_tag_mapping", ["tagId"], unique=False)
    op.create_index(op.f("ix_offer_tag_mapping_offerId"), "offer_tag_mapping", ["offerId"], unique=False)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            op.f("ix_offer_tag_mapping_offerId"),
            table_name="offer_tag_mapping",
            if_exists=True,
            postgresql_concurrently=True,
        )
        op.drop_index(
            op.f("ix_offer_tag_mapping_tagId"),
            table_name="offer_tag_mapping",
            if_exists=True,
            postgresql_concurrently=True,
        )
        op.drop_table("offer_tag_mapping", if_exists=True)
