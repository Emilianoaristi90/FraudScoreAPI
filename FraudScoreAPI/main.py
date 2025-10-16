# main.py — FraudScore API (v1.3.0)
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict
from datetime import datetime
from collections import defaultdict
from time import time
import logging, os

# -----------------------------
# App & Config
# -----------------------------
app = FastAPI(
    title="FraudScore API",
    version="1.3.0",
    description="API que calcula un puntaje de riesgo (0–100) para transacciones en tiempo real. Incluye API Key y rate limit por plan.",
)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("fraudscore")

API_KEY = os.getenv("API_KEY", "mi-clave-pro")
REQUESTS_PER_MIN = int(os.getenv("REQUESTS_PER_MIN", "60"))

# Reglas configurables por env (opcional)
SAFE_COUNTRIES = set(os.getenv("SAFE_COUNTRIES", "US,UK,ES,DE,FR,AR").split(","))
RISKY_IP_PREFIXES = [p for p in os.getenv("RISKY_IP_PREFIXES", "181.,190.,45.").split(",") if p]
HIGH_AMOUNT_THRESHOLD = float(os.getenv("HIGH_AMOUNT_THRESHOLD", "500"))
ODD_HOUR_START = int(os.getenv("ODD_HOUR_START", "23"))
ODD_HOUR_END = int(os.getenv("ODD_HOUR_END", "6"))
VELOCITY_LIMIT_10M = int(os.getenv("VELOCITY_LIMIT_10M", "4"))

# Rate limit por API KEY
_rate = defaultdict(list)  # api_key -> [timestamps]


# -----------------------------
# Modelos
# -----------------------------
class Transaction(BaseModel):
    transaction_id: str = Field(..., description="ID único de la transacción")
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


# -----------------------------
# Utilidades
# -----------------------------
def clamp(n: int, low=0, high=100) -> int:
    return max(low, min(high, n))

def risk_bucket(score: int) -> str:
    if score < 40:
        return "LOW"
    if score < 70:
        return "MEDIUM"
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

    # odd hour (23–23:59 o 00–06)
    if tx.hour >= ODD_HOUR_START or tx.hour <= ODD_HOUR_END:
        reasons["odd_hour"] = 20

    # ip prefix
    if any(tx.ip.startswith(pref) for pref in RISKY_IP_PREFIXES):
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

    # pequeño crédito si hay device_id conocido
    if tx.device_id:
        reasons["known_device_bonus"] = -5

    return reasons


# -----------------------------
# Middleware: Auth + Rate limit por API KEY
# -----------------------------
@app.middleware("http")
async def auth_and_ratelimit(request: Request, call_next):
    public_paths = {"/", "/docs", "/openapi.json", "/health", "/favicon.ico"}
    if request.url.path in public_paths:
        return await call_next(request)

    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    now = time()
    window = 60
    bucket = _rate[api_key]

    # limpia eventos fuera de ventana
    while bucket and now - bucket[0] > window:
        bucket.pop(0)

    if len(bucket) >= REQUESTS_PER_MIN:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    bucket.append(now)
    return await call_next(request)


# -----------------------------
# Endpoints
# -----------------------------
@app.get("/health", tags=["health"])
def health():
    return {"ok": True, "service": "FraudScore API", "version": app.version}


@app.post("/fraud-score", response_model=ScoreResponse, tags=["scoring"])
def get_fraud_score(
    tx: Transaction,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),  # solo para que Swagger muestre el header
):
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
        risk=bucket,  # type: ignore
        reasons=reasons,
        timestamp=ts,
    )


# -----------------------------
# Landing visual en "/"
# -----------------------------
@app.get("/", response_class=HTMLResponse)
def landing():
    host = os.getenv("PUBLIC_HOST", "fraudscoreapi.onrender.com")
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>FraudScore API</title>
<style>
  :root {{
    --bg:#0b0f17; --panel:#0f1524; --ink:#e8eef9; --muted:#9fb1d9;
    --line:#202a3c; --brand:#6ea8fe; --chip:#2a3342; --success:#58d38c;
  }}
  *{{box-sizing:border-box}} body{{margin:0;background:linear-gradient(180deg,#0b0f17 0%,#0a1222 100%);color:var(--ink);font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial}}
  .wrap{{max-width:1080px;margin:0 auto;padding:56px 20px}}
  .badge{{display:inline-block;padding:6px 10px;border:1px solid var(--chip);border-radius:999px;font-size:12px;color:var(--muted);letter-spacing:.3px}}
  h1{{font-size:46px;line-height:1.1;margin:14px 0 8px}}
  p{{color:var(--muted);font-size:16px;max-width:65ch}}
  .grid{{display:grid;grid-template-columns:1.2fr 1fr;gap:24px}}
  .card{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px}}
  .row{{display:flex;gap:12px;flex-wrap:wrap;margin-top:20px}}
  .btn{{background:var(--brand);border:0;color:#081018;padding:12px 16px;border-radius:10px;font-weight:700;text-decoration:none;display:inline-block}}
  .btn.secondary{{background:transparent;border:1px solid var(--line);color:var(--ink)}}
  .btn:hover{{filter:brightness(1.06)}}
  code,pre{{background:#0b1220;border:1px solid #1f2840;border-radius:10px;padding:12px;color:#d7e3ff;overflow:auto}}
  footer{{margin-top:40px;color:#7f8fb3;font-size:13px}}
  @media (max-width:900px){{.grid{{grid-template-columns:1fr}} h1{{font-size:38px}}}}
</style>
</head>
<body>
  <div class="wrap">
    <span class="badge">LIVE</span>
    <div class="grid" style="margin-top:10px">
      <div>
        <h1>FraudScore API</h1>
        <p>Calcula un puntaje de riesgo (0–100) para transacciones en tiempo real usando señales de país, IP, monto, horario, velocidad e integración 3DS. Autenticada por API Key y protegida con rate-limit por plan.</p>
        <div class="row">
          <a class="btn" href="/docs">Abrir Docs (Swagger)</a>
          <a class="btn secondary" href="mailto:emilianoaristi90@gmail.com">Contactar</a>
        </div>
        <div class="row" style="margin-top:14px">
          <span class="badge" style="border-color:#224c33;color:#98e2b1">Status: <b>UP</b> • v{app.version}</span>
        </div>
      </div>

      <div class="card">
        <strong>Ejemplo rápido (cURL)</strong>
        <pre><code>curl -X POST https://{host}/fraud-score \
  -H "Content-Type: application/json" \
  -H "X-API-Key: TU_API_KEY" \
  -d '{{"transaction_id":"tx_1","amount":780,"country":"RU","ip":"181.2.3.4","hour":23,"attempts_last_10m":6,"three_ds_result":"failed"}}'</code></pre>
      </div>
    </div>

    <div class="row" style="margin-top:22px">
      <div class="card" style="flex:1 1 280px"><strong>Auth</strong><br/>Header: <code>X-API-Key</code></div>
      <div class="card" style="flex:1 1 280px"><strong>Rate limit</strong><br/><code>{REQUESTS_PER_MIN} req/min</code> por API Key</div>
      <div class="card" style="flex:1 1 280px"><strong>Health</strong><br/><a href="/health">/health</a> (JSON)</div>
    </div>

    <footer>© 2025 FraudScore API · Desarrollado por Emiliano Aristi</footer>
  </div>
</body>
</html>
"""


# -----------------------------
# Run (solo local)
# -----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
