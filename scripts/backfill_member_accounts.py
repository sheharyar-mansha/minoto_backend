"""Backfill read-only login accounts for existing members (contacts).

For every contact that has no account yet, generate a one-time temp password and
mark it must-set-password. Prints the resulting `email -> temp password` list so
the owner can hand each member their first-login password.

Run from the backend folder:

    python -m scripts.backfill_member_accounts
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.session import SessionLocal  # noqa: E402
from models.contact import Contact  # noqa: E402
from utils.passwords import generate_temp_password  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        contacts = db.query(Contact).order_by(Contact.name.asc()).all()
        created: list[tuple[str, str, str]] = []
        for c in contacts:
            if c.hashed_password or c.temp_password:
                continue  # already has an account
            temp = generate_temp_password()
            c.temp_password = temp
            c.must_set_password = True
            db.add(c)
            created.append((c.name, c.email, temp))
        db.commit()

        if not created:
            print("No members needed an account — all set.")
            return

        print(f"Provisioned {len(created)} member account(s):\n")
        width = max(len(e) for _, e, _ in created)
        for name, email, temp in created:
            print(f"  {email:<{width}}  {temp}   ({name})")
        print("\nEach member logs in with the password above, then sets their own.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
