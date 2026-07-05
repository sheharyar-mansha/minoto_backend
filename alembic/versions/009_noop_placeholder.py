"""Placeholder revision (replaces an old destructive 009 that wiped the DB on upgrade).

Do not add logic here. For a full reset use scripts/nuclear_wipe_postgres.sql, then:
  python -m alembic stamp base && python -m alembic upgrade head
"""

from typing import Sequence, Union

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
