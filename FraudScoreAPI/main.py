# main.py — FraudScore API v2.0 (usuarios + API keys + cuotas + dashboard)
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from datetime import datetime
import logging

from db import init_db, get_session, ScoreLog
from auth import find_user_by_key, check_and_increment_quota, create_user, require_admin
from dashboard import render_dashboard
from sqlalchemy.orm import Session

# --------------------------------------------------------------------
# App + CORS + Logging
# --------------------------------------------------------------------
app = FastAPI(
    title="FraudScore API",
    description="Scoring antifraude con usuarios, API keys y cuotas por plan.",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fraudscore")

# Inicializa DB al arrancar
init_db()

# Swagger: botón Authorize con header X-API-Key
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()

# --------------------------------------------------------------------
# Modelos
# --------------------------------------------------------------------
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

# --------------------------------------------------------------------
# Scoring (reglas heurísticas)
# --------------------------------------------------------------------
def clamp(v: int) -> int:
    return max(0, min(v, 100))

def bucket(score: int) -> str:
    if score < 40:  return "LOW"
    if score < 70:  return "MEDIUM"
    return "HIGH"

def evaluate(tx: Transaction) -> dict:
    r = {}
    if tx.amount > 500:                 r["high_amount"] = 30
    if tx.country.upper() in {"RU","NG","UA","CN"}: r["untrusted_country"] = 20
    if tx.hour < 6 or tx.hour > 22:     r["odd_hour"] = 20
    if tx.ip.startswith(("181.","190.","45.")): r["risky_ip_prefix"] = 10
    if tx.attempts_last_10m > 3:        r["high_velocity"] = 25
    if tx.three_ds_result == "failed":  r["3ds_failed"] = 25
    return r

# --------------------------------------------------------------------
# Auth por API Key (usuario + cuota)
# --------------------------------------------------------------------
def require_user(
    db: Session = Depends(get_db),
    api_key: str | None = Depends(api_key_header)
):
    user = find_user_by_key(db, api_key or "")
    if not user:
        raise HTTPException(status_code=401, detail="unauthorized")
    # cuota mensual por plan
    check_and_increment_quota(db, user)
    return user

# --------------------------------------------------------------------
# Endpoints públicos
# --------------------------------------------------------------------
@app.get("/health", tags=["status"])
def health():
    return {"ok": True, "service": "FraudScore API", "version": app.version}

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home():
    return """
    <html>
      <head><title>FraudScore API</title>
      <style>
        body{font-family:Inter,system-ui;background:#0f1117;color:#e5e7eb;text-align:center;padding:56px}
        a.btn{display:inline-block;margin:8px;padding:12px 20px;border-radius:10px;background:#2563eb;color:#fff;text-decoration:none;font-weight:700}
        a.btn:hover{background:#1d4ed8} p{color:#9ca3af}
      </style></head>
      <body>
        <h1>FraudScore API</h1>
        <p>Scoring antifraude con API keys por usuario y cuotas por plan.</p>
        <a href="/docs" class="btn">Abrir Docs (Swagger)</a>
        <a href="/playground" class="btn" style="background:#6ea8fe;color:#0b1020">Abrir Playground</a>
        <p style="margin-top:28px;color:#6b7280">v2.0.0</p>
      </body>
    </html>
    """

# Playground simple: redirige a /docs (puedes mantener tu versión con HTML+JS si lo prefieres)
@app.get("/playground", response_class=HTMLResponse, include_in_schema=False)
def playground():
    return """
    <script>location.href='/docs';</script>
    Cargá el Playground desde Swagger (POST /fraud-score) usando tu API Key.
    """

# --------------------------------------------------------------------
# Endpoints de negocio (requieren API Key de usuario)
# --------------------------------------------------------------------
@app.post("/fraud-score", response_model=ScoreResponse, tags=["scoring"])
def fraud_score(tx: Transaction, user = Depends(require_user), db: Session = Depends(get_db)):
    try:
        reasons = evaluate(tx)
        total = clamp(int(round(sum(reasons.values()))))
        risk = bucket(total)
        ts = datetime.utcnow().isoformat() + "Z"

        # Log mínimo
        db.add(ScoreLog(user_id=user.id, amount=int(tx.amount), country=tx.country.upper(), risk=risk, score=total))
        db.commit()

        return ScoreResponse(fraud_score=total, risk=risk, reasons=reasons, timestamp=ts)
    except Exception as e:
        logging.exception("error in /fraud-score: %s", e)
        raise HTTPException(status_code=500, detail="internal_error")

# --------------------------------------------------------------------
# Uso del usuario y dashboard (requieren API Key)
# --------------------------------------------------------------------
@app.get("/me/usage", tags=["account"])
def my_usage(user = Depends(require_user)):
    return {
        "email": user.email,
        "plan": user.plan,
        "used_this_month": user.used_this_month,
        "monthly_quota": user.monthly_quota,
        "api_key_tail": user.api_key[-6:],
    }

@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def my_dashboard(user = Depends(require_user)):
    return render_dashboard(
        email=user.email,
        plan=user.plan,
        used=user.used_this_month,
        quota=user.monthly_quota,
        api_key=user.api_key
    )

# --------------------------------------------------------------------
# Admin: crear usuarios (protección por ADMIN_TOKEN)
# --------------------------------------------------------------------
@app.post("/admin/create-user", tags=["admin"])
def admin_create_user(email: str, plan: str = "free", admin_token: str = Header(None), db: Session = Depends(get_db)):
    require_admin(admin_token)
    u = create_user(db, email=email, plan=plan)
    return {"email": u.email, "plan": u.plan, "api_key": u.api_key, "monthly_quota": u.monthly_quota}

# --------------------------------------------------------------------
# Dev local
# --------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
