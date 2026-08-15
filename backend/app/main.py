from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.api import investigate
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
    question: str
    candidate_id: str | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
