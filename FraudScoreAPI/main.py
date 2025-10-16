from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime
import os
import logging

# -----------------------------
# Configuración
# -----------------------------
app = FastAPI(
    title="FraudScore API",
    version="1.2.0",
    description="API que calcula un puntaje de riesgo (0–100) para transacciones en tiempo real."
)

API_KEY = os.getenv("API_KEY", "mi-clave-pro")
REQUESTS_PER_MIN = 10
request_log = {}
logger = logging.getLogger("fraudscore")
logging.basicConfig(level=logging.INFO)

# -----------------------------
# Modelos
# -----------------------------
class Transaction(BaseModel):
    transaction_id: str
    amount: float
    country: str
    ip: str
    hour: int
    currency: str = "EUR"
    user_id: str | None = None
    device_id: str | None = None
    card_bin: str | None = None
    attempts_last_10m: int = 0
    three_ds_result: str = "success"


class ScoreResponse(BaseModel):
    fraud_score: int
    risk: str
    reasons: list[str]
    timestamp: str

# -----------------------------
# Funciones auxiliares
# -----------------------------
def calculate_fraud_score(tx: Transaction) -> ScoreResponse:
    score = 0
    reasons = []

    if tx.amount > 500:
        score += 30
        reasons.append("high_amount")
    if tx.country not in ["ES", "PT", "FR", "DE"]:
        score += 20
        reasons.append("untrusted_country")
    if tx.hour < 6 or tx.hour > 22:
        score += 20
        reasons.append("odd_hour")
    if tx.ip.startswith("181.") or tx.ip.startswith("45."):
        score += 10
        reasons.append("risky_ip_prefix")
    if tx.attempts_last_10m > 3:
        score += 25
        reasons.append("high_velocity")
    if tx.three_ds_result != "success":
        score += 25
        reasons.append("3ds_failed")

    bucket = "LOW" if score < 30 else "MEDIUM" if score < 70 else "HIGH"
    return ScoreResponse(
        fraud_score=min(score, 100),
        risk=bucket,
        reasons=reasons,
        timestamp=datetime.utcnow().isoformat() + "Z"
    )

# -----------------------------
# Middlewares de autenticación y rate limit
# -----------------------------
@app.middleware("http")
async def validate_api_key(request: Request, call_next):
    if request.url.path in ["/", "/docs", "/openapi.json", "/health"]:
        return await call_next(request)

    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    ip = request.client.host
    now = datetime.utcnow()
    window = now.replace(second=0, microsecond=0)
    request_log.setdefault(ip, {"window": window, "count": 0})

    if request_log[ip]["window"] != window:
        request_log[ip] = {"window": window, "count": 0}

    request_log[ip]["count"] += 1
    if request_log[ip]["count"] > REQUESTS_PER_MIN:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return await call_next(request)

# -----------------------------
# Endpoints
# -----------------------------
@app.get("/health")
def health():
    return {"ok": True, "service": "FraudScore API", "version": "1.2.0"}


@app.post("/fraud-score", response_model=ScoreResponse)
def fraud_score(tx: Transaction):
    result = calculate_fraud_score(tx)
    logger.info(f"tx={tx.transaction_id} amount={tx.amount} country={tx.country} "
                f"ip={tx.ip} score={result.fraud_score} risk={result.risk}")
    return result


@app.get("/", response_class=HTMLResponse)
def root():
    return """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>FraudScore API</title>
  <style>
    body{margin:0;background:#0b0f17;color:#e8eef9;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial}
    .wrap{max-width:900px;margin:0 auto;padding:56px 24px}
    .hero{display:flex;gap:28px;align-items:center;flex-wrap:wrap}
    .badge{display:inline-block;padding:6px 10px;border:1px solid #2a3342;border-radius:999px;font-size:12px;color:#b9c6e4}
    h1{font-size:40px;line-height:1.1;margin:14px 0 8px}
    p{color:#b9c6e4;font-size:16px;max-width:60ch}
    .card{background:#0f1524;border:1px solid #202a3c;border-radius:16px;padding:18px}
    .row{display:flex;gap:12px;flex-wrap:wrap;margin-top:20px}
    .btn{background:#6ea8fe;border:0;color:#081018;padding:12px 16px;border-radius:10px;font-weight:600;text-decoration:none}
    .btn:hover{filter:brightness(1.05)}
    code,pre{background:#0b1220;border:1px solid #1f2840;border-radius:10px;padding:12px;color:#d7e3ff}
    footer{margin-top:40px;color:#7f8fb3;font-size:13px}
  </style>
</head>
<body>
  <div class="wrap">
    <span class="badge">LIVE</span>
    <div class="hero">
      <div style="flex:1 1 420px">
        <h1>FraudScore API</h1>
        <p>Calcula un puntaje de riesgo (0–100) para transacciones en tiempo real usando reglas de país, IP, monto, horario y velocidad. Incluye API Key y rate-limit por plan.</p>
        <div class="row">
          <a class="btn" href="/docs">Ver Docs (Swagger)</a>
          <a class="btn" href="mailto:emilianoaristi90@gmail.com">Contactar</a>
        </div>
      </div>
      <div class="card" style="flex:1 1 360px">
        <strong>Ejemplo cURL</strong>
        <pre><code>curl -X POST https://fraudscoreapi.onrender.com/fraud-score \
  -H "Content-Type: application/json" \
  -H "X-API-Key: TU_API_KEY" \
  -d '{"transaction_id":"tx_1","amount":780,"country":"RU","ip":"181.2.3.4","hour":23,"attempts_last_10m":6,"three_ds_result":"failed"}'</code></pre>
      </div>
    </div>

    <div class="row">
      <div class="card" style="flex:1 1 280px">
        <strong>Auth</strong><br/>Header: <code>X-API-Key</code>
      </div>
      <div class="card" style="flex:1 1 280px">
        <strong>Rate limit</strong><br/><code>REQUESTS_PER_MIN</code> por API key
      </div>
      <div class="card" style="flex:1 1 280px">
        <strong>Docs</strong><br/><a href="/docs">/docs</a> (OpenAPI)
      </div>
    </div>

    <footer>© 2025 FraudScore API · v1.2.0</footer>
  </div>
</body>
</html>
"""
