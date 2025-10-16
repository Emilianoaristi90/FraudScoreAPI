# 🚀 FraudScore API

**FraudScore API** es un servicio inteligente que calcula un **puntaje de riesgo (0–100)** para detectar posibles fraudes en transacciones financieras, en tiempo real.  
Analiza patrones como monto, país, IP, hora, intentos recientes y resultado del 3DS para determinar si una operación es segura o sospechosa.

---

### 🌍 Demo pública

- **Base URL:** [https://fraudscoreapi.onrender.com](https://fraudscoreapi.onrender.com)  
- **Documentación Swagger:** [https://fraudscoreapi.onrender.com/docs](https://fraudscoreapi.onrender.com/docs)

---

## ⚙️ Características principales

✅ Detección de fraude en tiempo real  
✅ Score de riesgo (0 a 100) y nivel (`LOW`, `MEDIUM`, `HIGH`)  
✅ Autenticación mediante API Key  
✅ Rate limiting integrado  
✅ Desplegado con **Render** (FastAPI + Uvicorn)

---

## 🧩 Endpoints

### **1️⃣ /health — Verificar estado del servicio**

**GET** `/health`

✅ Verifica que el servicio esté activo.  
**Ejemplo de respuesta:**
```json
{
  "ok": true,
  "service": "FraudScore API",
  "version": "1.2.0"
}
2️⃣ /fraud-score — Obtener puntaje de riesgo
POST /fraud-score

Calcula el puntaje de riesgo basado en los datos enviados.

🔑 Headers requeridos:
makefile
Copiar código
X-API-Key: TU_API_KEY
Content-Type: application/json
📤 Ejemplo de request:
json
Copiar código
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
📥 Ejemplo de respuesta:
json
Copiar código
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
  "timestamp": "2025-10-16T16:30:00Z"
}
🧠 Campos admitidos
Campo	Tipo	Descripción
transaction_id	string	ID único de la transacción
amount	float	Monto de la operación
country	string	Código de país (ISO2 o ISO3)
ip	string	Dirección IP del cliente
hour	int	Hora (0–23)
currency	string	Moneda (ej: "EUR")
user_id	string	Identificador del usuario
device_id	string	Identificador del dispositivo
card_bin	string	Primeros 6 dígitos de la tarjeta
attempts_last_10m	int	Intentos recientes del mismo usuario
three_ds_result	string	"success", "failed", "unavailable"

🔐 Autenticación
Todas las peticiones requieren incluir el header:

makefile
Copiar código
X-API-Key: TU_API_KEY
Tu API Key se puede definir como variable de entorno en Render:

ini
Copiar código
API_KEY=mi-clave-pro
🧾 Ejemplo con cURL
bash
Copiar código
curl -X POST https://fraudscoreapi.onrender.com/fraud-score \
  -H "accept: application/json" \
  -H "X-API-Key: mi-clave-pro" \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "tx_001",
    "amount": 1200,
    "country": "BR",
    "ip": "190.85.22.7",
    "hour": 3,
    "currency": "USD",
    "attempts_last_10m": 4,
    "three_ds_result": "failed"
  }'
🛠️ Instalación local (para desarrollo)
bash
Copiar código
# Clonar el proyecto
git clone https://github.com/Emilianoaristi90/FraudScoreAPI.git
cd FraudScoreAPI/FraudScoreAPI

# Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar el servidor local
export API_KEY="mi-clave-pro"
uvicorn main:app --reload
Abrir en el navegador:
👉 http://127.0.0.1:8000/docs

🧩 Tecnologías utilizadas
🐍 Python 3.10+

⚡ FastAPI

🌐 Uvicorn

☁️ Render (Deploy automático)

📦 JSON REST API

📚 Versionado
Versión	Descripción	Fecha
1.0.0	Versión inicial local	2025-10-10
1.1.0	Integración con Render	2025-10-13
1.2.0	API pública en producción	2025-10-16

🧾 Licencia
© 2025 FraudScore API — Desarrollado por Emiliano Aristi.
Uso libre con atribución y para fines educativos o de prueba.
