# FraudScore API — v1.5.0 (API Key con botón Authorize + Playground público)
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from datetime import datetime
import logging
import os

# --------------------------------------------------------------------
# App & Config
# --------------------------------------------------------------------
app = FastAPI(
    title="FraudScore API",
    description="Calcula un puntaje de riesgo (0–100) para transacciones financieras en tiempo real.",
    version="1.5.0",
)

# CORS amplio (Swagger + navegador)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fraudscore")

API_KEY = os.getenv("API_KEY", "mi-clave-pro")          # en Render: API_KEY=fraud2025
RATE_LIMIT = int(os.getenv("REQUESTS_PER_MIN", "60"))   # en Render: REQUESTS_PER_MIN=60
_requests = {}  # memoria simple p/ rate limit

# Seguridad (esto hace que Swagger muestre el botón "Authorize")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def require_api_key(x_api_key: str | None = Depends(api_key_header)):
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")
    # rate limit por minuto y por API key
    now = int(datetime.utcnow().timestamp())
    window = now // 60
    key = f"{x_api_key}:{window}"
    _requests[key] = _requests.get(key, 0) + 1
    if _requests[key] > RATE_LIMIT:
        raise HTTPException(status_code=429, detail="rate_limit_exceeded")
    return True

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
# Reglas de scoring
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
# Endpoints
# --------------------------------------------------------------------
@app.get("/health", tags=["status"])
def health():
    return {"ok": True, "service": "FraudScore API", "version": app.version}

@app.post("/fraud-score", response_model=ScoreResponse, tags=["scoring"])
def fraud_score(tx: Transaction, _auth: bool = Depends(require_api_key)):
    try:
        reasons = evaluate(tx)
        total = clamp(int(round(sum(reasons.values()))))
        risk = bucket(total)
        ts = datetime.utcnow().isoformat() + "Z"

        logger.info(
            "tx=%s amount=%.2f country=%s ip=%s hour=%s score=%s bucket=%s reasons=%s",
            tx.transaction_id, tx.amount, tx.country, tx.ip, tx.hour, total, risk, list(reasons.keys())
        )

        return ScoreResponse(
            fraud_score=total,
            risk=risk,
            reasons=reasons,
            timestamp=ts
        )
    except Exception as e:
        logger.exception("error in /fraud-score: %s", e)
        raise HTTPException(status_code=500, detail="internal_error")

# --------------------------------------------------------------------
# Landing simple
# --------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home():
    return f"""
    <html>
      <head>
        <title>FraudScore API</title>
        <style>
          body {{ font-family: Inter, system-ui; background:#0f1117; color:#e5e7eb; text-align:center; padding:56px }}
          h1 {{ color:#fff; font-size:42px; margin:0 0 10px }}
          p  {{ color:#9ca3af; max-width:720px; margin:0 auto 20px }}
          a.btn {{ display:inline-block; margin:8px; padding:12px 20px; border-radius:10px; background:#2563eb; color:#fff; text-decoration:none; font-weight:700 }}
          a.btn:hover {{ background:#1d4ed8 }}
          footer {{ margin-top:28px; color:#6b7280; font-size:14px }}
        </style>
      </head>
      <body>
        <h1>FraudScore API</h1>
        <p>Calcula un puntaje de riesgo (0–100) para transacciones en tiempo real. Autenticación por API Key y documentación interactiva.</p>
        <a href="/docs" class="btn">Abrir Docs (Swagger)</a>
        <a href="/playground" class="btn" style="background:#6ea8fe;color:#0b1020">Abrir Playground</a>
        <footer>Estado: <b>UP</b> • v{app.version}</footer>
      </body>
    </html>
    """

# --------------------------------------------------------------------
# Playground público (HTML+JS)
# --------------------------------------------------------------------
@app.get("/playground", response_class=HTMLResponse, include_in_schema=False)
def playground():
    return """
<!doctype html>
<html lang="es"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>FraudScore • Playground</title>
<style>
  :root{--bg:#0b0f17;--panel:#0f1524;--ink:#e8eef9;--muted:#9fb1d9;--line:#202a3c;--brand:#6ea8fe;--good:#34d399;--warn:#fbbf24;--bad:#f87171}
  body{margin:0;background:linear-gradient(180deg,#0b0f17 0%,#0a1222 100%);color:var(--ink);font-family:Inter,system-ui}
  .wrap{max-width:1080px;margin:0 auto;padding:36px 16px}
  h1{margin:0 0 8px;font-size:28px} p{color:var(--muted);margin:0 0 18px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}
  label{font-size:13px;color:var(--muted)} input,select{width:100%;padding:10px;border-radius:10px;border:1px solid var(--line);background:#0c1322;color:var(--ink)}
  .row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .btn{background:var(--brand);border:0;color:#081018;padding:12px 16px;border-radius:10px;font-weight:700;cursor:pointer}
  pre{background:#0b1220;border:1px solid #1f2840;border-radius:10px;padding:12px;color:#d7e3ff;overflow:auto}
  .badge{display:inline-block;padding:6px 10px;border-radius:999px;font-weight:700}
</style></head>
<body>
<div class="wrap">
  <h1>FraudScore • Playground</h1>
  <p>Probá la API desde el navegador. Colocá tu API Key, completa los campos y envía.</p>

  <div class="grid">
    <div class="card">
      <div class="row">
        <div><label>API Key</label><input id="apiKey" placeholder="X-API-Key" /></div>
        <div><label>Transaction ID</label><input id="tx" placeholder="tx_001" /></div>
      </div>
      <div class="row">
        <div><label>Monto</label><input id="amount" type="number" step="0.01" value="890" /></div>
        <div><label>Hora (0–23)</label><input id="hour" type="number" min="0" max="23" value="23" /></div>
      </div>
      <div class="row">
        <div><label>País (ISO2)</label><input id="country" value="RU" /></div>
        <div><label>IP</label><input id="ip" value="181.45.77.2" /></div>
      </div>
      <div class="row">
        <div><label>Intentos últimos 10m</label><input id="attempts" type="number" min="0" value="6" /></div>
        <div><label>3DS</label>
          <select id="threeDS">
            <option value="success">success</option>
            <option value="failed" selected>failed</option>
            <option value="unavailable">unavailable</option>
          </select>
        </div>
      </div>
      <div style="margin-top:14px">
        <button class="btn" id="sendBtn">Calcular Score</button>
      </div>
    </div>

    <div class="card">
      <div style="display:flex;align-items:center;gap:10px; margin-bottom:10px">
        <span>Resultado</span>
        <span id="badge" class="badge" style="background:#374151">—</span>
      </div>
      <pre id="output">Aún no hay respuesta.</pre>
    </div>
  </div>
</div>

<script>
  const $ = (id) => document.getElementById(id);
  const HOST = window.location.origin;

  $('sendBtn').addEventListener('click', async () => {
    const key = $('apiKey').value.trim();
    if (!key) { alert('Pon tu X-API-Key'); return; }

    const payload = {
      transaction_id: $('tx').value || 'tx_demo',
      amount: parseFloat($('amount').value || '0'),
      country: $('country').value || 'ES',
      ip: $('ip').value || '8.8.8.8',
      hour: parseInt($('hour').value || '0'),
      attempts_last_10m: parseInt($('attempts').value || '0'),
      three_ds_result: $('threeDS').value || 'success'
    };

    $('output').textContent = 'Enviando...';

    try {
      const res = await fetch(HOST + '/fraud-score', {
        method: 'POST',
        headers: { 'Content-Type':'application/json', 'X-API-Key': key },
        body: JSON.stringify(payload)
      });
      const text = await res.text();
      let data; try { data = JSON.parse(text); } catch { data = { raw: text }; }
      $('output').textContent = JSON.stringify(data, null, 2);

      const risk = (data && data.risk) ? String(data.risk).toUpperCase() : '—';
      const color = risk === 'HIGH' ? 'var(--bad)' : risk === 'MEDIUM' ? 'var(--warn)' : risk === 'LOW' ? 'var(--good)' : '#374151';
      const b = $('badge'); b.textContent = risk; b.style.background = color; b.style.color = '#0b0f17';
    } catch (e) {
      $('output').textContent = 'Error: ' + e;
      alert('Error de red');
    }
  });
</script>
</body></html>
"""

# --------------------------------------------------------------------
# Local dev
# --------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
