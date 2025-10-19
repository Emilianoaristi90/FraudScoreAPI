from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, date
import os, time, json, secrets
from db import get_db, User, ScoreLog
from auth import find_user_by_key, ensure_month_window
from dashboard import evaluate, bucket, clamp
import logging

# --- CONFIG BASE ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fraudscore")

app = FastAPI(
    title="FraudScore API",
    description="API para calcular puntaje de fraude en tiempo real.",
    version="1.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DEMO + FRONT CONFIG ---
DEMO_ENABLED = os.getenv("DEMO_ENABLED", "true").lower() == "true"
API_KEY_FALLBACK = os.getenv("API_KEY_FALLBACK")
DEMO_RPM = 10
_rate_bucket = {}  # ip -> (minute_window, count)

def demo_allowed(ip: str) -> bool:
    """Simple rate limit per IP for demo mode"""
    now = int(time.time())
    win = now // 60
    last, cnt = _rate_bucket.get(ip, (win, 0))
    if last != win:
        _rate_bucket[ip] = (win, 0)
        last, cnt = win, 0
    if cnt >= DEMO_RPM:
        return False
    _rate_bucket[ip] = (last, cnt + 1)
    return True


# --- MODELOS ---
class Transaction(BaseModel):
    transaction_id: str
    amount: float
    country: str
    ip: str
    hour: int
    attempts_last_10m: int
    three_ds_result: str


class ScoreResponse(BaseModel):
    fraud_score: int
    risk: str
    reasons: dict
    timestamp: str


# --- ENDPOINT PRINCIPAL ---
@app.post("/fraud-score", response_model=ScoreResponse, tags=["scoring"])
def fraud_score(
    tx: Transaction,
    api_key: str = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    user = find_user_by_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="unauthorized_api_key")

    ensure_month_window(user)
    if user.used_this_month >= user.monthly_quota:
        raise HTTPException(status_code=429, detail="quota_exceeded")

    try:
        reasons = evaluate(tx)
        total = clamp(int(round(sum(reasons.values()))))
        risk = bucket(total)
        ts = datetime.utcnow().isoformat() + "Z"

        db.add(
            ScoreLog(
                user_id=user.id,
                amount=int(tx.amount),
                country=tx.country.upper(),
                risk=risk,
                score=total,
            )
        )
        user.used_this_month += 1
        db.commit()

        return ScoreResponse(fraud_score=total, risk=risk, reasons=reasons, timestamp=ts)
    except Exception:
        db.rollback()
        logger.exception("Error en /fraud-score")
        raise HTTPException(status_code=500, detail="internal_error")


# --- ENDPOINT DEMO ---
@app.post("/demo/fraud-score", response_model=ScoreResponse, tags=["demo"])
def demo_fraud_score(tx: Transaction, request: Request, db: Session = Depends(get_db)):
    if not (DEMO_ENABLED and API_KEY_FALLBACK):
        raise HTTPException(status_code=403, detail="demo_disabled")

    ip = request.headers.get("CF-Connecting-IP") or request.client.host
    if not demo_allowed(ip):
        raise HTTPException(status_code=429, detail="demo_rate_limited")

    class PseudoUser:
        id = 0
        email = "demo@fraudscore.local"
        plan = "starter"
        used_this_month = 0
        monthly_quota = 1000
        api_key = API_KEY_FALLBACK

    user = PseudoUser()

    try:
        reasons = evaluate(tx)
        total = clamp(int(round(sum(reasons.values()))))
        risk = bucket(total)
        ts = datetime.utcnow().isoformat() + "Z"

        try:
            db.add(
                ScoreLog(
                    user_id=user.id,
                    amount=int(tx.amount),
                    country=tx.country.upper(),
                    risk=risk,
                    score=total,
                )
            )
            db.commit()
        except Exception:
            db.rollback()

        return ScoreResponse(fraud_score=total, risk=risk, reasons=reasons, timestamp=ts)
    except Exception:
        logger.exception("Error en /demo/fraud-score")
        raise HTTPException(status_code=500, detail="internal_error")


# --- FRONTEND / PLAYGROUND ---
@app.get("/playground", response_class=HTMLResponse, include_in_schema=False)
def playground():
    demo_badge = "Demo habilitado" if (DEMO_ENABLED and API_KEY_FALLBACK) else "Demo deshabilitado"
    demo_on = "true" if (DEMO_ENABLED and API_KEY_FALLBACK) else "false"

    return f"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>FraudScore • Playground</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
  <style>body{{font-family:Inter,system-ui}}</style>
</head>
<body class="bg-slate-950 text-slate-100">
  <div class="max-w-6xl mx-auto px-4 py-8">
    <div class="flex items-center justify-between gap-4">
      <h1 class="text-3xl font-bold">FraudScore • Playground</h1>
      <div class="text-sm text-slate-400">{demo_badge}</div>
    </div>
    <p class="text-slate-400 mt-1">Probá la API sin salir del navegador. Usá tu <code class="bg-slate-800 px-2 py-0.5 rounded">X-API-Key</code> o activá <span class="font-semibold">Modo Demo</span>.</p>

    <div class="grid md:grid-cols-2 gap-6 mt-6">
      <!-- FORM -->
      <div class="bg-slate-900/60 border border-slate-800 rounded-2xl p-5">
        <div class="flex items-center gap-3 mb-4">
          <input id="demoToggle" type="checkbox" class="h-4 w-4 rounded border-slate-700" />
          <label for="demoToggle" class="text-slate-300">Usar <span class="font-semibold">Modo Demo</span> (sin API Key)</label>
        </div>

        <div id="apiKeyRow" class="mb-4">
          <label class="block text-sm text-slate-300 mb-1">API Key (header <b>X-API-Key</b>)</label>
          <input id="apiKey" class="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2" placeholder="pega tu API Key aquí" />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm text-slate-300 mb-1">Monto</label>
            <input id="amount" type="number" value="890" class="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2" />
          </div>
          <div>
            <label class="block text-sm text-slate-300 mb-1">Hora (0–23)</label>
            <input id="hour" type="number" value="23" class="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2" />
          </div>
          <div>
            <label class="block text-sm text-slate-300 mb-1">País (ISO2)</label>
            <input id="country" value="RU" class="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2" />
          </div>
          <div>
            <label class="block text-sm text-slate-300 mb-1">Intentos últimos 10m</label>
            <input id="attempts" type="number" value="6" class="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2" />
          </div>
          <div class="col-span-2">
            <label class="block text-sm text-slate-300 mb-1">IP</label>
            <input id="ip" value="181.45.77.2" class="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2" />
          </div>
          <div class="col-span-2">
            <label class="block text-sm text-slate-300 mb-1">3DS</label>
            <select id="threeDS" class="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2">
              <option value="success">success</option>
              <option selected value="failed">failed</option>
              <option value="unavailable">unavailable</option>
            </select>
          </div>
        </div>

        <button id="runBtn" class="mt-5 inline-flex items-center gap-2 bg-blue-500 hover:bg-blue-600 text-slate-950 font-semibold px-4 py-2 rounded-lg">
          Calcular Score
        </button>
      </div>

      <!-- RESULT -->
      <div class="bg-slate-900/60 border border-slate-800 rounded-2xl p-5">
        <div class="flex items-center justify-between">
          <div class="text-slate-300">Resultado</div>
          <div id="pill" class="px-3 py-1 rounded-full text-sm font-semibold bg-slate-800 border border-slate-700">…</div>
        </div>
        <pre id="out" class="mt-3 text-sm bg-slate-950/60 border border-slate-800 rounded-xl p-3 overflow-auto min-h-[260px]"></pre>
      </div>
    </div>

    <div class="mt-6 text-slate-400 text-sm">
      ¿Documentación? <a class="text-blue-400 underline" href="/docs">/docs</a>
    </div>
  </div>

<script>
  const DEMO_ON = {demo_on};
  const demoToggle = document.getElementById('demoToggle');
  const apiKeyRow  = document.getElementById('apiKeyRow');
  const apiKey     = document.getElementById('apiKey');
  const pill       = document.getElementById('pill');
  const out        = document.getElementById('out');

  demoToggle.checked = DEMO_ON;
  apiKeyRow.style.display = DEMO_ON ? 'none' : 'block';

  demoToggle.addEventListener('change', ()=> {{
    apiKeyRow.style.display = demoToggle.checked ? 'none' : 'block';
  }});

  function riskPill(risk) {{
    const map = {{
      LOW:    'bg-emerald-400 text-emerald-950',
      MEDIUM: 'bg-amber-400 text-amber-950',
      HIGH:   'bg-rose-400 text-rose-950'
    }};
    pill.className = 'px-3 py-1 rounded-full text-sm font-semibold '+(map[risk]||'bg-slate-800');
    pill.textContent = risk || '…';
  }}

  document.getElementById('runBtn').addEventListener('click', async () => {{
    const body = {{
      transaction_id: 'tx_demo',
      amount: parseFloat(document.getElementById('amount').value||0),
      country: document.getElementById('country').value.trim(),
      ip: document.getElementById('ip').value.trim(),
      hour: parseInt(document.getElementById('hour').value||0),
      attempts_last_10m: parseInt(document.getElementById('attempts').value||0),
      three_ds_result: document.getElementById('threeDS').value
    }};

    try {{
      let url = '/fraud-score';
      let headers = {{'Content-Type':'application/json'}};

      if (demoToggle.checked) {{
        url = '/demo/fraud-score';
      }} else {{
        const k = apiKey.value.trim();
        if (!k) throw new Error('Pegá tu API Key o activa Modo Demo.');
        headers['X-API-Key'] = k;
      }}

      const r = await fetch(url, {{
        method: 'POST',
        headers,
        body: JSON.stringify(body)
      }});

      const data = await r.json();
      if (!r.ok) throw new Error((data && data.detail) || 'Error');

      riskPill(data.risk);
      out.textContent = JSON.stringify(data, null, 2);
    }} catch(e) {{
      riskPill('');
      out.textContent = JSON.stringify({{error: e.message}}, null, 2);
    }}
  }});
</script>
</body>
</html>
"""
# --- HEALTH CHECK ---
@app.get("/health")
def health():
    return {"ok": True, "service": "FraudScore API", "version": app.version}
