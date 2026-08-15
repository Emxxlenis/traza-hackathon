# TRAZA

> Tú traes la pregunta. TRAZA hace la investigación.

Agente de investigación sobre datos públicos colombianos (RUES, SECOP, Procuraduría,
Contraloría vía Croma). Convierte una pregunta en lenguaje natural en un expediente donde
cada hallazgo es evidencia trazable: `direct` (lo dice la fuente) o `derived` (calculado, con
cadena reproducible). No acusamos — investigamos.

## Estructura

- `backend/` — FastAPI. `croma_client/` (wrapper REST), `agent/` (loop de investigación),
  `evidence/` (Evidence Layer), `app/` (API HTTP).
- `ui/` — React + Vite. Input en lenguaje natural, desambiguación, vista de expediente.
- `docs/contracts/` — contratos de datos entre módulos.
- `data/raw/` — capturas crudas de Croma (fuera de git).

## Correr

Backend (requiere Python 3.12+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env   # completar claves
uvicorn app.main:app --reload
```

UI:

```bash
cd ui
npm install
npm run dev
```

Configuración vía `.env` en la raíz — ver `.env.example`.

Notas:

- La UI llama al backend en `http://localhost:8000` por defecto; se cambia con `VITE_API_URL`
  (ej. en `ui/.env.local`) si ese puerto está ocupado — correr entonces
  `uvicorn app.main:app --port 8010`.
- `VITE_USE_MOCK=1` corre la UI contra fixtures ficticios (sin backend), con banner de
  "DATOS DE PRUEBA" visible.
