from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from datetime import datetime
import os

# Inicialización
app = FastAPI(
    title="FraudScore API",
    description="Calcula un puntaje de riesgo (0–100) para transacciones financieras en tiempo real.",
    version="1.4.2",
)

# Permitir acceso desde Swagger y otros orígenes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================
# 🔐 Autenticación por API Key
# ==============================
API_KEY = os.getenv("API_KEY", "mi-clave-pro")

def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

# ==============================
# 📦 Modelo de entrada
# ==============================
class FraudRequest(BaseModel):
    transaction_id: str
    amount: float
    country: str
    ip: str
    hour: int
    attempts_last_10m: int
    three_ds_result: str

# ==============================
# 🌍 Endpoints
# ==============================
@app.get("/health")
def health_check():
    return {"ok": True, "service": "FraudScore API", "version": "1.4.2"}

@app.post("/fraud-score")
def fraud_score(data: FraudRequest, valid: bool = verify_api_key()):
    # Simulación simple del cálculo de riesgo
    score = 0
    reasons = {}

    if data.amount > 500:
        score += 30
        reasons["high_amount"] = 30
    if data.country.upper() in ["RU", "CN", "NG"]:
        score += 20
        reasons["untrusted_country"] = 20
    if data.hour < 6 or data.hour > 22:
        score += 20
        reasons["odd_hour"] = 20
    if data.attempts_last_10m > 3:
        score += 25
        reasons["high_velocity"] = 25
    if data.three_ds_result.lower() == "failed":
        score += 25
        reasons["3ds_failed"] = 25

    risk = "LOW" if score < 40 else "MEDIUM" if score < 70 else "HIGH"

    return {
        "fraud_score": score,
        "risk": risk,
        "reasons": reasons,
        "timestamp": datetime.utcnow().isoformat()
    }

# ==============================
# ⚙️ Personalizar OpenAPI (para botón Authorize)
# ==============================
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="FraudScore API",
        version="1.4.2",
        description="API que calcula puntaje de riesgo de fraude en tiempo real.",
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "APIKeyHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
        }
    }
    openapi_schema["security"] = [{"APIKeyHeader": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
