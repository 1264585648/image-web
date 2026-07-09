"""Assign pre-auth images and tasks to a legacy user.

Usage from the backend container or backend working directory:

    python scripts/migrate_legacy_user_data.py legacy@example.com "ChangeMe123!" "Legacy Demo"

This is intentionally explicit instead of automatic. It prevents old anonymous records
from being silently assigned to the wrong real account after auth is enabled.
"""

from __future__ import annotations

import sys
from uuid import uuid4

from app.auth import hash_password, normalize_email
from app.database import SessionLocal, init_db
from app.models import GenerationTask, SourceImage, User


def main() -> int:
    if len(sys.argv) < 3:
        print('Usage: python scripts/migrate_legacy_user_data.py <email> <password> [display_name]')
        return 2

    email = normalize_email(sys.argv[1])
    password = sys.argv[2]
    display_name = sys.argv[3] if len(sys.argv) >= 4 else 'Legacy Demo'

    init_db()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(
                id=str(uuid4()),
                email=email,
                password_hash=hash_password(password),
                display_name=display_name,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f'Created legacy user: {email}')
        else:
            print(f'Using existing user: {email}')

        image_count = db.query(SourceImage).filter(SourceImage.user_id.is_(None)).update({SourceImage.user_id: user.id})
        task_count = db.query(GenerationTask).filter(GenerationTask.user_id.is_(None)).update({GenerationTask.user_id: user.id})
        db.commit()
        print(f'Assigned {image_count} source images and {task_count} generation tasks to {email}.')
        return 0
    finally:
        db.close()


if __name__ == '__main__':
    raise SystemExit(main())
