# FraudScore API

Minimal, production-ready **fraud scoring API** built with FastAPI.  
It receives a transaction payload and returns a risk score (0-100) and bucket (LOW / MEDIUM / HIGH) with reasons.

## 🚀 Quickstart (local)

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Open the interactive docs at: http://127.0.0.1:8000/docs

### Sample request (POST /fraud-score)

```json
{
  "transaction_id": "tx_123",
  "amount": 750,
  "country": "RU",
  "ip": "181.45.77.2",
  "hour": 23,
  "currency": "EUR",
  "user_id": "user_9",
  "device_id": null,
  "card_bin": null,
  "attempts_last_10m": 6,
  "three_ds_result": "failed"
}
```

### Sample response
```json
{
  "fraud_score": 83,
  "risk": "HIGH",
  "reasons": {
    "high_amount": 30,
    "untrusted_country": 20,
    "odd_hour": 20,
    "risky_ip_prefix": 10,
    "high_velocity": 25,
    "3ds_failed": 25
  },
  "timestamp": "2025-10-13T12:00:00Z"
}
```

## ⚙️ Configuration

You can tune behavior via environment variables:

- `SAFE_COUNTRIES` (comma-separated, default: `US,UK,ES,DE,FR,AR`)
- `RISKY_IP_PREFIXES` (comma-separated, default: `181.,190.,45.`)
- `HIGH_AMOUNT_THRESHOLD` (default: `500`)
- `ODD_HOUR_START` (default: `23`)
- `ODD_HOUR_END` (default: `6`)
- `VELOCITY_LIMIT_10M` (default: `4`)
- `LOG_LEVEL` (default: `INFO`)

## 🧪 cURL test

```bash
curl -X POST http://127.0.0.1:8000/fraud-score \
  -H "Content-Type: application/json" \
  -d @sample_request.json
```

## ☁️ Deploy (Render or Railway)

### Render (free)
1. Push this folder to a public GitHub repo.
2. Create a **Web Service** on Render, connect the repo.
3. Set:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port 10000`
4. Add environment variables as needed.
5. Deploy.

### Railway (free)
1. Create a new project → **Deploy from GitHub** (or upload).
2. Railway autodetects Python.
3. Set **Start Command** to:
   ```
   uvicorn main:app --host 0.0.0.0 --port ${PORT}
   ```

## 🔒 Notes

- This is **rule-based** by design (MVP). You can later add ML, IP reputation APIs, device fingerprint, etc.
- Logging is enabled; avoid logging sensitive data in production.

## 📄 License
MIT
