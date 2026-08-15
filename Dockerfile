# TRAZA — imagen single-origin: FastAPI sirve API + UI compilada.
# Variables requeridas en runtime: CROMA_API_KEY, CROMA_BASE_URL, OPENAI_API_KEY,
# LLM_PROVIDER=openai, LLM_MODEL=gpt-5.6-terra. Opcionales: RATE_LIMIT_PER_IP_HOUR,
# RATE_LIMIT_GLOBAL_HOUR, PORT.

FROM node:22-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
# Mismo origen: la UI llama /investigate relativo.
ENV VITE_API_URL=
RUN npm run build

FROM python:3.12-slim
WORKDIR /app/backend
COPY backend/ /app/backend/
RUN pip install --no-cache-dir /app/backend
COPY --from=ui /ui/dist /app/ui/dist
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
