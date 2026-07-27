"""
Run once to create the super admin user.
Usage: docker compose run --rm fastapi python -m app.db.seed
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from app.db.connection import SessionLocal
from app.db.models import User
from app.auth.login import hash_password

SUPER_ADMIN_EMAIL = "admin@projecta.com"
SUPER_ADMIN_PASSWORD = "changeme123!"   # change after first login
SUPER_ADMIN_NAME = "Super Admin"


def seed():
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == SUPER_ADMIN_EMAIL).first()
        if existing:
            print(f"Super admin already exists: {SUPER_ADMIN_EMAIL}")
            return

        user = User(
            email=SUPER_ADMIN_EMAIL,
            hashed_password=hash_password(SUPER_ADMIN_PASSWORD),
            full_name=SUPER_ADMIN_NAME,
            role="super_admin",
            organisation_id=None
        )
        db.add(user)
        db.commit()
        print(f"✅ Super admin created: {SUPER_ADMIN_EMAIL}")
        print(f"   Password: {SUPER_ADMIN_PASSWORD}")
        print(f"   Change this password immediately after first login.")
    finally:
        db.close()
    
if __name__ == "__main__":
    seed()
