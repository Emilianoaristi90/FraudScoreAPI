from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any
from datetime import datetime
import logging
import os
import time

# ---- Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("fraudscore")

app = FastAPI(
    title="FraudScore API",
    description="Fraud scoring API with API key and rate limiting.",
    version="1.2.0",
)

# ---- API key + Rate limit
API_KEY = os.getenv("API_KEY", "dev-key")  # cámbiala en producción
REQUESTS_PER_MIN = int(os.getenv("REQUESTS_PER_MIN", "60"))
_rate_bucket = {}  # key -> lista de timestamps últimos 60s

def rate_limit_check(key: str):
    now = time.time()
    window = 60
    bucket = _rate_bucket.setdefault(key, [])
    while bucket and now - bucket[0] > window:
        bucket.pop(0)
    if len(bucket) >= REQUESTS_PER_MIN:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bucket.append(now)

# ---- Modelos
class Transaction(BaseModel):
    transaction_id: str = Field(..., description="Unique transaction identifier")
    amount: float = Field(..., ge=0)
    country: str = Field(..., min_length=2, max_length=3)
    ip: str
    hour: int = Field(..., ge=0, le=23)
    currency: Optional[str] = "EUR"
    user_id: Optional[str] = None
    device_id: Optional[str] = None
    card_bin: Optional[str] = None
    attempts_last_10m: Optional[int] = 0
    three_ds_result: Optional[Literal["success", "failed", "unavailable"]] = None

class ScoreResponse(BaseModel):
    fraud_score: int
    risk: Literal["LOW", "MEDIUM", "HIGH"]
    reasons: Dict[str, int]
    timestamp: str

# ---- Config reglas
SAFE_COUNTRIES = set((os.getenv("SAFE_COUNTRIES","US,UK,ES,DE,FR,AR").split(",")))
RISKY_IP_PREFIXES = os.getenv("RISKY_IP_PREFIXES", "181.,190.,45.").split(",")
HIGH_AMOUNT_THRESHOLD = float(os.getenv("HIGH_AMOUNT_THRESHOLD", "500"))
ODD_HOUR_START = int(os.getenv("ODD_HOUR_START", "23"))
ODD_HOUR_END = int(os.getenv("ODD_HOUR_END", "6"))
VELOCITY_LIMIT_10M = int(os.getenv("VELOCITY_LIMIT_10M", "4"))

def clamp(n, low=0, high=100):
    return max(low, min(high, int(round(n))))

def risk_bucket(score: int) -> str:
    if score < 40: return "LOW"
    if score < 70: return "MEDIUM"
    return "HIGH"

def evaluate_rules(tx: Transaction) -> Dict[str, int]:
    reasons: Dict[str, int] = {}

    # amount
    if tx.amount >= HIGH_AMOUNT_THRESHOLD:
        reasons["high_amount"] = 30
    elif tx.amount >= HIGH_AMOUNT_THRESHOLD * 0.6:
        reasons["mid_amount"] = 15

    # country
    if tx.country.upper() not in SAFE_COUNTRIES:
        reasons["untrusted_country"] = 20

    # hour (23–23:59 or 00–06)
    if tx.hour >= ODD_HOUR_START or tx.hour <= ODD_HOUR_END:
        reasons["odd_hour"] = 20

    # ip prefix
    if any(tx.ip.startswith(pref) for pref in RISKY_IP_PREFIXES if pref):
        reasons["risky_ip_prefix"] = 10

    # velocity
    attempts = tx.attempts_last_10m or 0
    if attempts > VELOCITY_LIMIT_10M:
        reasons["high_velocity"] = 25
    elif attempts >= max(1, VELOCITY_LIMIT_10M - 1):
        reasons["elevated_velocity"] = 10

    # 3DS
    if tx.three_ds_result == "failed":
        reasons["3ds_failed"] = 25
    elif tx.three_ds_result == "unavailable":
        reasons["3ds_unavailable"] = 8

    # device bonus
    if tx.device_id:
        reasons["known_device_bonus"] = -5

    return reasons

@app.get("/", tags=["health"])
def health() -> Dict[str, Any]:
    return {"ok": True, "service": "FraudScore API", "version": "1.2.0"}

@app.post("/fraud-score", response_model=ScoreResponse, tags=["scoring"])
def get_fraud_score(
    tx: Transaction,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    # auth + rate limit
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    rate_limit_check(x_api_key)

    reasons = evaluate_rules(tx)
    total = clamp(sum(reasons.values()))
    bucket = risk_bucket(total)
    ts = datetime.utcnow().isoformat() + "Z"

    logger.info("tx=%s amount=%.2f country=%s ip=%s hour=%s score=%s bucket=%s reasons=%s",
                tx.transaction_id, tx.amount, tx.country, tx.ip, tx.hour, total, bucket, list(reasons.keys()))

    return ScoreResponse(
        fraud_score=total,
        risk=bucket,
        reasons=reasons,
        timestamp=ts
    )
