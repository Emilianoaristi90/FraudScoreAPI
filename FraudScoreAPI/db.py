# db.py — conexión y modelos (SQLAlchemy)
import os
from datetime import datetime, date
from sqlalchemy import (
    create_engine, Integer, String, DateTime, Date, BigInteger,
    func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

# Si no se define DATABASE_URL en Render, usa SQLite local
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///fraudscore.db")

class Base(DeclarativeBase):
    pass

# Tabla de usuarios
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    api_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(32), default="free")   # free/starter/pro/business
    monthly_quota: Mapped[int] = mapped_column(Integer, default=100)
    used_this_month: Mapped[int] = mapped_column(Integer, default=0)
    usage_month: Mapped[Date] = mapped_column(Date, default=date.today)

# Tabla de logs de scoring
class ScoreLog(Base):
    __tablename__ = "score_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    amount: Mapped[int] = mapped_column(Integer, default=0)
    country: Mapped[str] = mapped_column(String(8), default="")
    risk: Mapped[str] = mapped_column(String(16), default="LOW")
    score: Mapped[int] = mapped_column(Integer, default=0)

# Configuración del motor
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args=({} if not DATABASE_URL.startswith("sqlite") else {"check_same_thread": False}),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def init_db():
    """Inicializa las tablas en la base de datos."""
    Base.metadata.create_all(bind=engine)

def get_session():
    """Crea una sesión de base de datos (para usar en cada request)."""
    return SessionLocal()
