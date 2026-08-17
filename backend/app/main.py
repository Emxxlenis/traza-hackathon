import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from agent.api import investigate
from app import ratelimit
from app.ratelimit import check_rate_limit
from auth import db as auth_db
from auth.api import require_user
from auth.api import router as auth_router

logger = logging.getLogger("traza.app")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Prepara la base de cuentas al arrancar y suelta el pool al terminar."""
    auth_db.check_production_storage()
    await auth_db.init_db()
    if not auth_db.is_persistent():
        logger.warning(
            "Cuentas en SQLite (%s): en un contenedor efímero se pierden al redesplegar. "
            "Producción debe definir DATABASE_URL apuntando a Postgres.",
            auth_db.database_url(),
        )
    yield
    await auth_db.dispose_engine()


app = FastAPI(title="TRAZA", version="0.1.0", lifespan=lifespan)

# Dev: la UI de Vite corre en 5173. Producción es single-origin (misma URL),
# así que no necesita CORS. allow_credentials es obligatorio para que el
# navegador mande la cookie de sesión en el flujo de desarrollo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


class InvestigateRequest(BaseModel):
    # max_length acota el costo por request en un endpoint público (la pregunta
    # entra al prompt del LLM); la UI impone el mismo tope en el textarea.
    question: str = Field(min_length=1, max_length=1000)
    candidate_id: str | None = Field(default=None, max_length=200)

    @field_validator("question")
    @classmethod
    def _require_non_blank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("la pregunta no puede estar vacía")
        return value


@app.get("/health")
async def health() -> dict:
    """Salud + configuración operacional no-secreta (verificable desde afuera)."""
    return {
        "status": "ok",
        "rate_limit_per_ip_hour": ratelimit.PER_IP_PER_HOUR,
        "rate_limit_global_hour": ratelimit.GLOBAL_PER_HOUR,
        "auth_required": True,
        # False = las cuentas están en SQLite y no sobreviven un redeploy.
        # Verificable desde afuera, sin exponer la URL de la base.
        "accounts_persistent": auth_db.is_persistent(),
    }


# require_user va ANTES del rate limit a propósito: un request sin sesión debe
# salir con 401 sin gastar cupo de la hora (si no, cualquiera podría agotar la
# cuota global de la instancia sin siquiera tener cuenta).
@app.post("/investigate", dependencies=[Depends(require_user), Depends(check_rate_limit)])
async def investigate_route(req: InvestigateRequest) -> dict:
    """Corre la investigación y devuelve el expediente según el contrato v0.1.

    La desambiguación viaja por el mismo endpoint: un CaseFile con
    status=needs_disambiguation trae candidates[], y el cliente reenvía la
    misma pregunta con candidate_id.
    """
    case = await investigate(req.question, candidate_id=req.candidate_id)
    return case.to_contract_dict()


# --- Streaming de progreso (NDJSON) -----------------------------------------
# El POST /investigate clásico queda intacto como fallback; este endpoint emite
# los MISMOS resultados más eventos de progreso reales del loop del agente.

# Si no hay eventos en este intervalo se emite {"type": "ping"} para que los
# proxies intermedios no corten la conexión por inactividad.
PING_INTERVAL_SECONDS = 10.0

STREAM_ERROR_DETAIL = (
    "No pudimos completar la investigación en este momento. "
    "Tu pregunta no se perdió: puedes reintentar."
)

# Sentinela interno de fin de stream (nunca se serializa).
_STREAM_DONE = object()


def _ndjson_line(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False, default=str) + "\n"


@app.post(
    "/investigate/stream",
    dependencies=[Depends(require_user), Depends(check_rate_limit)],
)
async def investigate_stream_route(req: InvestigateRequest) -> StreamingResponse:
    """Igual que /investigate pero emitiendo progreso EN VIVO como NDJSON.

    Una línea JSON por evento REAL del loop del agente (consultas a fuentes y
    fase de ensamblado; nunca pasos simulados) y, al final, una línea
    {"type": "result", "case_file": {...}} con el mismo contrato del POST
    clásico, o {"type": "error", "detail": "..."} si la investigación falló.
    Comparte la dependency de rate limit: una investigación = un cupo,
    streaming o no.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue()

    def on_event(event: dict[str, Any]) -> None:
        # Callback SYNC del loop del agente. En el hilo del event loop se
        # encola DIRECTO (call_soon_threadsafe aplazaría el evento a la
        # siguiente vuelta y la línea "result" podría adelantarlo); desde otro
        # hilo, call_soon_threadsafe es la vía segura.
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            queue.put_nowait(event)
        else:
            loop.call_soon_threadsafe(queue.put_nowait, event)

    async def _run_investigation() -> None:
        try:
            case = await investigate(
                req.question, candidate_id=req.candidate_id, on_event=on_event
            )
            queue.put_nowait({"type": "result", "case_file": case.to_contract_dict()})
        except Exception:
            logger.exception("la investigación en streaming falló")
            queue.put_nowait({"type": "error", "detail": STREAM_ERROR_DETAIL})
        finally:
            queue.put_nowait(_STREAM_DONE)

    async def _stream() -> AsyncIterator[str]:
        task = asyncio.create_task(_run_investigation())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=PING_INTERVAL_SECONDS)
                except TimeoutError:
                    yield _ndjson_line({"type": "ping"})
                    continue
                if event is _STREAM_DONE:
                    break
                yield _ndjson_line(event)
        finally:
            # Cliente desconectado o stream terminado: nunca dejar la task viva.
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    return StreamingResponse(
        _stream(),
        media_type="application/x-ndjson",
        # Anti-buffering: sin esto, proxies tipo nginx agrupan las líneas y el
        # progreso deja de ser "en vivo".
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Producción single-origin: la UI compilada se sirve desde el mismo FastAPI.
# Montado al final para que /investigate y /health resuelvan primero.
_UI_DIST = Path(__file__).resolve().parents[2] / "ui" / "dist"
if _UI_DIST.is_dir():
    app.mount("/", StaticFiles(directory=_UI_DIST, html=True), name="ui")
