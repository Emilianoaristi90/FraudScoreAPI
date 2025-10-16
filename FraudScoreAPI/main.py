from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from datetime import datetime
import logging
import os

app = FastAPI(title="FraudScore API", version="1.3.0")

# --- CONFIGURACIÓN ---
API_KEY = os.getenv("API_KEY", "mi-clave-pro")
RATE_LIMIT = 60  # requests/min por API Key
requests_log = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fraudscore")


# --- MODELOS ---
class Transaction(BaseModel):
    transaction_id: str
    amount: float
    country: str
    ip: str
    hour: int
    attempts_last_10m: int = 0
    three_ds_result: str = "success"


class ScoreResponse(BaseModel):
    fraud_score: int
    risk: str
    reasons: dict
    timestamp: str


# --- FUNCIONES ---
def clamp(value: int) -> int:
    return max(0, min(value, 100))


def risk_bucket(score: int) -> str:
    if score < 40:
        return "LOW"
    elif score < 70:
        return "MEDIUM"
    return "HIGH"


def evaluate_rules(tx: Transaction) -> dict:
    """Evalúa señales de riesgo simples"""
    reasons = {}
    if tx.amount > 500:
        reasons["high_amount"] = 30
    if tx.country in ["RU", "NG", "UA", "CN"]:
        reasons["untrusted_country"] = 20
    if tx.hour < 6 or tx.hour > 22:
        reasons["odd_hour"] = 20
    if tx.ip.startswith(("181.", "190.", "45.")):
        reasons["risky_ip_prefix"] = 10
    if tx.attempts_last_10m > 3:
        reasons["high_velocity"] = 25
    if tx.three_ds_result == "failed":
        reasons["3ds_failed"] = 25
    return reasons


# --- MIDDLEWARE ---
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """Autenticación básica + rate limit"""
    if request.url.path not in ["/", "/health", "/docs", "/openapi.json"]:
        api_key = request.headers.get("X-API-Key")
        if api_key != API_KEY:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        now = datetime.utcnow().timestamp()
        window = int(now // 60)
        key = f"{api_key}:{window}"
        requests_log[key] = requests_log.get(key, 0) + 1
        if requests_log[key] > RATE_LIMIT:
            return JSONResponse({"error": "rate_limit_exceeded"}, status_code=429)

    response = await call_next(request)
    return response


# --- ENDPOINTS ---
@app.get("/health", tags=["status"])
def health():
    return {"ok": True, "service": "FraudScore API", "version": "1.3.0"}


@app.post("/fraud-score", response_model=ScoreResponse, tags=["scoring"])
def get_fraud_score(tx: Transaction):
    try:
        reasons = evaluate_rules(tx)
        total = clamp(int(round(sum(reasons.values()))))
        bucket = risk_bucket(total)
        ts = datetime.utcnow().isoformat() + "Z"

        logger.info(
            "tx=%s amount=%.2f country=%s ip=%s hour=%s score=%s bucket=%s reasons=%s",
            tx.transaction_id, tx.amount, tx.country, tx.ip, tx.hour, total, bucket, list(reasons.keys())
        )

        return ScoreResponse(
            fraud_score=total,
            risk=bucket,
            reasons=reasons,
            timestamp=ts,
        )
    except Exception as e:
        logger.exception("Unhandled error in /fraud-score: %s", e)
        raise HTTPException(status_code=500, detail="internal_error")


# --- LANDING VISUAL ---
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home():
    return """
    <html>
      <head>
        <title>FraudScore API</title>
        <style>
          body { font-family: Inter, sans-serif; background-color: #0f1117; color: #e5e7eb; text-align: center; padding: 60px; }
          h1 { font-size: 2.8rem; color: white; margin-bottom: 10px; }
          p { color: #9ca3af; font-size: 1.1rem; max-width: 650px; margin: 0 auto 30px; }
          a.btn { display: inline-block; margin: 10px; padding: 12px 22px; border-radius: 10px; background: #2563eb; color: white; text-decoration: none; font-weight: bold; }
          a.btn:hover { background: #1d4ed8; }
          pre { text-align: left; background: #1f2937; padding: 18px; border-radius: 10px; overflow-x: auto; max-width: 720px; margin: 30px auto; }
          .tag { background: #10b981; color: white; padding: 4px 10px; border-radius: 8px; font-size: 0.8rem; }
          footer { margin-top: 40px; color: #6b7280; font-size: 0.9rem; }
        </style>
      </head>
      <body>
        <div class="tag">LIVE</div>
        <h1>FraudScore API</h1>
        <p>Calcula un puntaje de riesgo (0–100) para transacciones en tiempo real usando señales de país, IP, monto, horario, velocidad y 3DS. Autenticada por API Key y protegida con rate-limit.</p>
        <a href="/docs" class="btn">Abrir Docs (Swagger)</a>
        <a href="mailto:emiliano@example.com" class="btn">Contactar</a>

        <pre><b>Ejemplo rápido (cURL)</b>
curl -X POST https://fraudscoreapi.onrender.com/fraud-score \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: mi-clave-pro" \\
  -d '{
    "transaction_id": "tx_001",
    "amount": 890,
    "country": "RU",
    "ip": "181.45.77.2",
    "hour": 23,
    "attempts_last_10m": 7,
    "three_ds_result": "failed"
  }'
        </pre>

        <footer>© 2025 FraudScore API · Desarrollado por Emiliano Aristi</footer>
      </body>
    </html>
    """
