"""Add final_elapsed_seconds to meetings for transcript re-runs."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column("final_elapsed_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("meetings", "final_elapsed_seconds")
