# auth.py — helpers de autenticación, cuotas y planes
import os
import secrets
from datetime import date
from sqlalchemy.orm import Session
from fastapi import HTTPException
from db import User

# Planes disponibles y su cuota mensual
PLANS = {
    "free": 100,
    "starter": 1000,
    "pro": 10000,
    "business": 100000,
}

# Token de administrador (para crear usuarios)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")  # define esto en Render

def generate_api_key() -> str:
    """Genera una API key aleatoria."""
    return secrets.token_urlsafe(28)

def find_user_by_key(db: Session, api_key: str) -> User | None:
    """Busca un usuario por su API Key."""
    if not api_key:
        return None
    return db.query(User).filter(User.api_key == api_key).first()

def ensure_month_window(user: User):
    """Resetea contador de cuota al cambiar de mes."""
    today = date.today().replace(day=1)
    if user.usage_month != today:
        user.usage_month = today
        user.used_this_month = 0
        user.monthly_quota = PLANS.get(user.plan, PLANS["free"])

def check_and_increment_quota(db: Session, user: User):
    """Verifica cuota mensual y la incrementa."""
    ensure_month_window(user)
    if user.used_this_month >= user.monthly_quota:
        raise HTTPException(status_code=429, detail="monthly_quota_exceeded")
    user.used_this_month += 1
    db.add(user)
    db.commit()

def create_user(db: Session, email: str, plan: str = "free") -> User:
    """Crea un nuevo usuario con su API Key."""
    api = generate_api_key()
    u = User(
        email=email,
        api_key=api,
        plan=plan,
        monthly_quota=PLANS.get(plan, PLANS["free"]),
        used_this_month=0,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

def require_admin(token: str | None):
    """Protege endpoints solo para admin."""
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized_admin")
