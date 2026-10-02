"""add default pickup time slots

Revision ID: 20261002_0071
Revises: 20261001_0070
Create Date: 2026-10-02 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20261002_0071'
down_revision: Union[str, None] = '20261001_0070'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    slots_data = [
        ("09:00:00", "12:00:00", "09:00–12:00", 1),
        ("12:00:00", "15:00:00", "12:00–15:00", 2),
        ("15:00:00", "18:00:00", "15:00–18:00", 3),
        ("18:00:00", "21:00:00", "18:00–21:00", 4),
        ("21:00:00", "22:00:00", "21:00–22:00", 5),
    ]
    for start_t, end_t, label, sort_order in slots_data:
        op.execute(
            sa.text(f"""
                INSERT INTO delivery_time_slots 
                (delivery_type, pickup_point_id, start_time, end_time, label, weekdays, orders_limit, sort_order, is_active, created_date, updated_date)
                SELECT 'pickup', NULL, '{start_t}'::time, '{end_t}'::time, '{label}', '0,1,2,3,4,5,6', 50, {sort_order}, true, timezone('Europe/Moscow', now()), timezone('Europe/Moscow', now())
                WHERE NOT EXISTS (
                    SELECT 1 FROM delivery_time_slots WHERE delivery_type = 'pickup' AND start_time = '{start_t}'::time AND end_time = '{end_t}'::time
                );
            """)
        )


def downgrade() -> None:
    op.execute(
        sa.text("""
            DELETE FROM delivery_time_slots
            WHERE delivery_type = 'pickup'
              AND pickup_point_id IS NULL
              AND label IN ('09:00–12:00', '12:00–15:00', '15:00–18:00', '18:00–21:00', '21:00–22:00');
        """)
    )
