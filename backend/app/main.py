from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from agent.api import investigate
from app import ratelimit
from app.ratelimit import check_rate_limit

app = FastAPI(title="TRAZA", version="0.1.0")

# Dev: la UI de Vite corre en 5173. Producción real queda como roadmap (spec §2).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    }


@app.post("/investigate", dependencies=[Depends(check_rate_limit)])
async def investigate_route(req: InvestigateRequest) -> dict:
    """Corre la investigación y devuelve el expediente según el contrato v0.1.

    La desambiguación viaja por el mismo endpoint: un CaseFile con
    status=needs_disambiguation trae candidates[], y el cliente reenvía la
    misma pregunta con candidate_id.
    """
    case = await investigate(req.question, candidate_id=req.candidate_id)
    return case.to_contract_dict()


# Producción single-origin: la UI compilada se sirve desde el mismo FastAPI.
# Montado al final para que /investigate y /health resuelvan primero.
_UI_DIST = Path(__file__).resolve().parents[2] / "ui" / "dist"
if _UI_DIST.is_dir():
    app.mount("/", StaticFiles(directory=_UI_DIST, html=True), name="ui")
