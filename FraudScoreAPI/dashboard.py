# dashboard.py — mini dashboard HTML para ver uso por API key
def render_dashboard(email: str, plan: str, used: int, quota: int, api_key: str):
    remain = max(0, quota - used)
    return f"""
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>FraudScore • Dashboard</title>
<style>
  body{{font-family:Inter,system-ui;background:#0f1117;color:#e5e7eb;margin:0;padding:36px}}
  .wrap{{max-width:900px;margin:0 auto}}
  h1{{margin:0 0 10px}} p{{color:#9ca3af}}
  .card{{background:#0f1524;border:1px solid #202a3c;border-radius:14px;padding:16px;margin-top:14px}}
  code{{background:#0b1220;border:1px solid #1f2840;border-radius:6px;padding:2px 6px;color:#d7e3ff}}
  .grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
  a.btn{{display:inline-block;margin-top:10px;padding:10px 14px;border-radius:10px;background:#6ea8fe;color:#0b1020;text-decoration:none;font-weight:700}}
</style>
</head>
<body>
<div class="wrap">
  <h1>FraudScore • Dashboard</h1>
  <p>Estado de tu API Key y uso mensual.</p>

  <div class="card grid">
    <div><b>Email</b><br>{email}</div>
    <div><b>Plan</b><br>{plan}</div>
    <div><b>Usado este mes</b><br>{used}</div>
    <div><b>Cuota mensual</b><br>{quota} (restan {remain})</div>
  </div>

  <div class="card">
    <b>Tu API Key:</b> <code>{api_key}</code>
    <p style="color:#9ca3af">Úsala en el header <code>X-API-Key</code> al llamar <code>/fraud-score</code>.</p>
    <a class="btn" href="/docs">Abrir Docs (Swagger)</a>
    <a class="btn" href="/playground">Abrir Playground</a>
  </div>
</div>
</body>
</html>
"""
