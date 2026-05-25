"""add previous_generation_id foreign key constraint

Revision ID: n1o2p3q4r5s6
Revises: m0n1o2p3q4r5
Create Date: 2026-09-16 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n1o2p3q4r5s6"
down_revision: Union[str, Sequence[str], None] = "m0n1o2p3q4r5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add FK constraint on previous_generation_id referencing generation_provenance.generation_id."""
    op.create_foreign_key(
        "fk_generation_provenance_previous_generation_id",
        "generation_provenance",
        "generation_provenance",
        ["previous_generation_id"],
        ["generation_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Remove FK constraint on previous_generation_id."""
    op.drop_constraint(
        "fk_generation_provenance_previous_generation_id",
        "generation_provenance",
        type_="foreignkey",
    )
