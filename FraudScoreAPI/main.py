# main.py — FraudScore API (v1.4.1) con Playground público
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from datetime import datetime
import logging
import os

app = FastAPI(title="FraudScore API", version="1.4.1")

# --- CONFIGURACIÓN ---
API_KEY = os.getenv("API_KEY", "mi-clave-pro")
RATE_LIMIT = int(os.getenv("REQUESTS_PER_MIN", "60"))  # requests/min por API Key
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
    if tx.country.upper() in ["RU", "NG", "UA", "CN"]:
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


# --- MIDDLEWARE (Auth + Rate limit por API key) ---
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    # Rutas públicas (no requieren API Key)
    public_paths = {"/", "/health", "/docs", "/openapi.json", "/favicon.ico"}
    if request.url.path in public_paths or request.url.path.startswith("/playground"):
        return await call_next(request)

    # Auth por API Key (para el resto, p.ej. /fraud-score)
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    # Rate limit simple por API key (ventana de 60s)
    now = int(datetime.utcnow().timestamp())
    window = now // 60
    key = f"{api_key}:{window}"
    requests_log[key] = requests_log.get(key, 0) + 1
    if requests_log[key] > RATE_LIMIT:
        return JSONResponse({"error": "rate_limit_exceeded"}, status_code=429)

    return await call_next(request)


# --- ENDPOINTS ---
@app.get("/health", tags=["status"])
def health():
    return {"ok": True, "service": "FraudScore API", "version": app.version}


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


# --- LANDING PRINCIPAL ---
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home():
    return """
    <html>
      <head>
        <title>FraudScore API</title>
        <style>
          body { font-family: Inter, ui-sans-serif, system-ui; background-color: #0f1117; color: #e5e7eb; text-align: center; padding: 56px; }
          h1 { font-size: 2.8rem; color: white; margin-bottom: 12px; }
          p { color: #9ca3af; font-size: 1.1rem; max-width: 720px; margin: 0 auto 28px; }
          a.btn { display: inline-block; margin: 10px; padding: 12px 22px; border-radius: 10px; background: #2563eb; color: white; text-decoration: none; font-weight: bold; }
          a.btn:hover { background: #1d4ed8; }
          .row { margin-top: 12px; }
          .tag { background: #10b981; color: white; padding: 4px 10px; border-radius: 8px; font-size: 0.8rem; }
          footer { margin-top: 40px; color: #6b7280; font-size: 0.9rem; }
        </style>
      </head>
      <body>
        <div class="tag">LIVE</div>
        <h1>FraudScore API</h1>
        <p>Calcula un puntaje de riesgo (0–100) para transacciones en tiempo real usando señales de país, IP, monto, horario, velocidad y 3DS.</p>
        <div class="row">
          <a href="/docs" class="btn">Abrir Docs (Swagger)</a>
          <a href="/playground" class="btn" style="background:#6ea8fe;color:#0b0f17;">Abrir Playground</a>
        </div>
        <footer>© 2025 FraudScore API · Desarrollado por Emiliano Aristi</footer>
      </body>
    </html>
    """


# --- PLAYGROUND (público) ---
@app.get("/playground", response_class=HTMLResponse, include_in_schema=False)
def playground():
    return """
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>FraudScore • Playground</title>
<style>
  :root{--bg:#0b0f17;--panel:#0f1524;--ink:#e8eef9;--muted:#9fb1d9;--line:#202a3c;--brand:#6ea8fe;--good:#34d399;--warn:#fbbf24;--bad:#f87171}
  *{box-sizing:border-box} body{margin:0;background:linear-gradient(180deg,#0b0f17 0%,#0a1222 100%);color:var(--ink);font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial}
  .wrap{max-width:1100px;margin:0 auto;padding:36px 16px}
  h1{margin:0 0 8px;font-size:28px} p{color:var(--muted);margin:0 0 20px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}
  label{font-size:13px;color:var(--muted)} input,select{width:100%;padding:10px;border-radius:10px;border:1px solid var(--line);background:#0c1322;color:var(--ink)}
  .row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .btn{background:var(--brand);border:0;color:#081018;padding:12px 16px;border-radius:10px;font-weight:700;cursor:pointer}
  .btn:disabled{opacity:.6;cursor:not-allowed}
  pre{background:#0b1220;border:1px solid #1f2840;border-radius:10px;padding:12px;color:#d7e3ff;overflow:auto}
  .badge{display:inline-block;padding:6px 10px;border-radius:999px;font-weight:700}
</style>
</head>
<body>
  <div class="wrap">
    <h1>FraudScore • Playground</h1>
    <p>Proba la API sin salir del navegador. Completa el formulario y envía la transacción para ver el score y las razones.</p>

    <div class="grid">
      <div class="card">
        <div class="row">
          <div>
            <label>API Key</label>
            <input id="apiKey" placeholder="X-API-Key" />
          </div>
          <div>
            <label>Transaction ID</label>
            <input id="tx" placeholder="tx_001" />
          </div>
        </div>

        <div class="row">
          <div>
            <label>Monto</label>
            <input id="amount" type="number" step="0.01" value="890" />
          </div>
          <div>
            <label>Hora (0–23)</label>
            <input id="hour" type="number" min="0" max="23" value="23" />
          </div>
        </div>

        <div class="row">
          <div>
            <label>País (ISO2)</label>
            <input id="country" placeholder="ES" value="RU" />
          </div>
          <div>
            <label>IP</label>
            <input id="ip" placeholder="181.45.77.2" value="181.45.77.2" />
          </div>
        </div>

        <div class="row">
          <div>
            <label>Intentos últimos 10 min</label>
            <input id="attempts" type="number" min="0" value="6" />
          </div>
          <div>
            <label>3DS</label>
            <select id="threeDS">
              <option value="success">success</option>
              <option value="failed" selected>failed</option>
              <option value="unavailable">unavailable</option>
            </select>
          </div>
        </div>

        <div style="margin-top:14px;display:flex;gap:10px">
          <button class="btn" id="sendBtn">Calcular Score</button>
          <button class="btn" id="saveBtn" style="background:#34d399">Guardar valores</button>
        </div>
        <p style="color:var(--muted);font-size:12px;margin-top:8px">El botón “Guardar valores” recuerda tu API Key y campos localmente.</p>
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

  // Cargar guardados
  window.addEventListener('DOMContentLoaded', () => {
    const savedKey = localStorage.getItem('fs_api_key');
    if (savedKey) $('apiKey').value = savedKey;

    const savedForm = JSON.parse(localStorage.getItem('fs_form') || "{}");
    for (const [k,v] of Object.entries(savedForm)) {
      if ($(k)) $(k).value = v;
    }
  });

  $('saveBtn').addEventListener('click', () => {
    localStorage.setItem('fs_api_key', $('apiKey').value);
    const form = {
      tx: $('tx').value,
      amount: $('amount').value,
      hour: $('hour').value,
      country: $('country').value,
      ip: $('ip').value,
      attempts: $('attempts').value,
      threeDS: $('threeDS').value
    };
    localStorage.setItem('fs_form', JSON.stringify(form));
    alert('Guardado ✅');
  });

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

    $('sendBtn').disabled = true;
    $('output').textContent = 'Enviando...';

    try {
      const res = await fetch(HOST + '/fraud-score', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': key
        },
        body: JSON.stringify(payload)
      });

      const text = await res.text();
      let data;
      try { data = JSON.parse(text); } catch { data = { raw: text }; }

      $('output').textContent = JSON.stringify(data, null, 2);

      // Badge / color
      const risk = (data && data.risk) ? String(data.risk).toUpperCase() : '—';
      const badge = $('badge');
      badge.textContent = risk;

      const color = risk === 'HIGH' ? 'var(--bad)' : risk === 'MEDIUM' ? 'var(--warn)' : risk === 'LOW' ? 'var(--good)' : '#374151';
      badge.style.background = color;
      badge.style.color = '#0b0f17';

      if (!res.ok) {
        console.warn('HTTP', res.status, data);
        alert('Error ' + res.status + (data && data.detail ? (': ' + data.detail) : ''));
      }
    } catch (e) {
      $('output').textContent = 'Error: ' + e;
      alert('Error de red o CORS');
    } finally {
      $('sendBtn').disabled = false;
    }
  });
</script>
</body>
</html>
"""


# --- MAIN LOCAL ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
