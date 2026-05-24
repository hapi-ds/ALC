"""add_signature_certificate_columns

Revision ID: g4h5i6j7k8l9
Revises: f3a4b5c6d7e8
Create Date: 2026-06-20 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "g4h5i6j7k8l9"
down_revision: Union[str, Sequence[str], None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add certificate columns to signature_records for PAdES mode support."""
    op.add_column(
        "signature_records",
        sa.Column("certificate_subject", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "signature_records",
        sa.Column("certificate_issuer", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "signature_records",
        sa.Column("certificate_serial", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "signature_records",
        sa.Column(
            "signature_mode",
            sa.String(length=10),
            nullable=False,
            server_default="hash",
        ),
    )


def downgrade() -> None:
    """Remove certificate columns from signature_records."""
    op.drop_column("signature_records", "signature_mode")
    op.drop_column("signature_records", "certificate_serial")
    op.drop_column("signature_records", "certificate_issuer")
    op.drop_column("signature_records", "certificate_subject")
