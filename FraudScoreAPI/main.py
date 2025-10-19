from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import os, time, json, math

app = FastAPI(
    title="FraudScore API",
    description="API pública para detección de fraude en tiempo real (versión simple).",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- CONFIGURACIÓN ----------------
API_KEYS = [k.strip() for k in os.getenv("API_KEYS", "fraud2025-demo").split(",")]
API_KEY_FALLBACK = os.getenv("API_KEY_FALLBACK", "fraud2025-demo")
DEMO_RPM = 10
_rate_bucket = {}

def demo_allowed(ip: str) -> bool:
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

# ---------------- MODELOS ----------------
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

# ---------------- LÓGICA DE SCORING ----------------
def evaluate(tx: Transaction) -> dict:
    reasons = {}
    if tx.amount > 1000: reasons["high_amount"] = 30
    if tx.country.upper() in ["RU", "NG", "BR"]: reasons["untrusted_country"] = 20
    if tx.hour < 6 or tx.hour > 22: reasons["odd_hour"] = 20
    if tx.attempts_last_10m > 3: reasons["high_velocity"] = 25
    if tx.three_ds_result.lower() == "failed": reasons["3ds_failed"] = 25
    return reasons

def clamp(x: int) -> int:
    return max(0, min(100, x))

def bucket(score: int) -> str:
    if score < 30: return "LOW"
    if score < 70: return "MEDIUM"
    return "HIGH"

# ---------------- ENDPOINTS ----------------

@app.post("/fraud-score", response_model=ScoreResponse, tags=["scoring"])
def fraud_score(tx: Transaction, api_key: str = Header(None, alias="X-API-Key")):
    if not api_key or api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="unauthorized_api_key")

    reasons = evaluate(tx)
    score = clamp(sum(reasons.values()))
    risk = bucket(score)
    ts = datetime.utcnow().isoformat() + "Z"

    return ScoreResponse(fraud_score=score, risk=risk, reasons=reasons, timestamp=ts)

@app.post("/demo/fraud-score", response_model=ScoreResponse, tags=["demo"])
def demo_fraud_score(tx: Transaction, request: Request):
    ip = request.client.host
    if not demo_allowed(ip):
        raise HTTPException(status_code=429, detail="demo_rate_limited")

    reasons = evaluate(tx)
    score = clamp(sum(reasons.values()))
    risk = bucket(score)
    ts = datetime.utcnow().isoformat() + "Z"

    return ScoreResponse(fraud_score=score, risk=risk, reasons=reasons, timestamp=ts)

# ---------------- PLAYGROUND VISUAL ----------------
@app.get("/playground", response_class=HTMLResponse, include_in_schema=False)
def playground():
    return HTMLResponse("""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>FraudScore • Playground</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
  <style>body{font-family:Inter,system-ui}</style>
</head>
<body class="bg-slate-950 text-slate-100">
  <div class="max-w-5xl mx-auto px-4 py-8">
    <h1 class="text-3xl font-bold mb-2">FraudScore • Playground</h1>
    <p class="text-slate-400 mb-6">Probá la API en vivo. Modo demo sin API Key disponible.</p>
    <div class="grid md:grid-cols-2 gap-6">
      <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl">
        <label class="block text-sm mb-1 text-slate-300">API Key (opcional)</label>
        <input id="apiKey" class="w-full mb-3 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2" placeholder="X-API-Key o vacío para demo">
        <div class="grid grid-cols-2 gap-3">
          <input id="amount" type="number" placeholder="Monto" value="890" class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2">
          <input id="hour" type="number" placeholder="Hora" value="23" class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2">
          <input id="country" value="RU" placeholder="País" class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2">
          <input id="attempts" type="number" value="6" placeholder="Intentos 10m" class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2">
          <input id="ip" value="181.45.77.2" placeholder="IP" class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 col-span-2">
          <select id="threeDS" class="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 col-span-2">
            <option value="success">3DS Success</option>
            <option value="failed" selected>3DS Failed</option>
            <option value="unavailable">3DS Unavailable</option>
          </select>
        </div>
        <button id="runBtn" class="mt-4 bg-blue-500 hover:bg-blue-600 text-slate-950 font-semibold px-4 py-2 rounded-lg">Calcular Score</button>
      </div>
      <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl">
        <div class="flex justify-between">
          <div class="text-slate-300">Resultado</div>
          <div id="risk" class="px-3 py-1 rounded-full text-sm font-semibold bg-slate-800 border border-slate-700">—</div>
        </div>
        <pre id="out" class="mt-3 text-sm bg-slate-950/60 border border-slate-800 rounded-xl p-3 overflow-auto min-h-[260px]"></pre>
      </div>
    </div>
  </div>
<script>
const btn=document.getElementById('runBtn'),out=document.getElementById('out'),riskEl=document.getElementById('risk');
btn.onclick=async()=>{
  const body={
    transaction_id:"tx_demo",
    amount:parseFloat(document.getElementById('amount').value),
    country:document.getElementById('country').value,
    ip:document.getElementById('ip').value,
    hour:parseInt(document.getElementById('hour').value),
    attempts_last_10m:parseInt(document.getElementById('attempts').value),
    three_ds_result:document.getElementById('threeDS').value
  };
  let url="/fraud-score",headers={"Content-Type":"application/json"};
  const key=document.getElementById('apiKey').value.trim();
  if(!key){url="/demo/fraud-score"} else headers["X-API-Key"]=key;
  const res=await fetch(url,{method:"POST",headers,body:JSON.stringify(body)});
  const data=await res.json();
  riskEl.textContent=data.risk||"—";
  out.textContent=JSON.stringify(data,null,2);
};
</script>
</body></html>
    """)

# ---------------- LANDING DE PRECIOS ----------------
@app.get("/pricing", response_class=HTMLResponse, include_in_schema=False)
def pricing():
    return HTMLResponse("""
<!doctype html><html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FraudScore • Pricing</title>
<script src="https://cdn.tailwindcss.com"></script>
</head><body class="bg-slate-950 text-slate-100">
<div class="max-w-5xl mx-auto px-4 py-10">
<h1 class="text-4xl font-bold mb-2">Planes y precios</h1>
<p class="text-slate-400 mb-8">Elige el plan que se adapte a tu negocio.</p>
<div class="grid md:grid-cols-3 gap-6">
  <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6">
    <h2 class="text-xl font-semibold mb-2">Starter</h2>
    <p class="text-slate-400 mb-4">1.000 requests / mes</p>
    <p class="text-3xl font-bold mb-4">$9<span class="text-base text-slate-400">/mes</span></p>
    <a href="mailto:contacto@fraudscoreapi.com?subject=Plan Starter" class="block text-center bg-blue-500 hover:bg-blue-600 text-slate-950 font-semibold px-4 py-2 rounded-lg">Comprar</a>
  </div>
  <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6">
    <h2 class="text-xl font-semibold mb-2">Pro</h2>
    <p class="text-slate-400 mb-4">10.000 requests / mes</p>
    <p class="text-3xl font-bold mb-4">$39<span class="text-base text-slate-400">/mes</span></p>
    <a href="mailto:contacto@fraudscoreapi.com?subject=Plan Pro" class="block text-center bg-blue-500 hover:bg-blue-600 text-slate-950 font-semibold px-4 py-2 rounded-lg">Comprar</a>
  </div>
  <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6">
    <h2 class="text-xl font-semibold mb-2">Business</h2>
    <p class="text-slate-400 mb-4">100.000 requests / mes</p>
    <p class="text-3xl font-bold mb-4">$149<span class="text-base text-slate-400">/mes</span></p>
    <a href="mailto:contacto@fraudscoreapi.com?subject=Plan Business" class="block text-center bg-blue-500 hover:bg-blue-600 text-slate-950 font-semibold px-4 py-2 rounded-lg">Contactar</a>
  </div>
</div>
<p class="mt-10 text-sm text-slate-400">¿Necesitas algo personalizado? <a href="mailto:contacto@fraudscoreapi.com" class="text-blue-400 underline">Contáctanos</a></p>
</div>
</body></html>
    """)

@app.get("/health")
def health():
    return {"ok": True, "service": "FraudScore API", "version": app.version}
