"""Loopback research API. Run with uvicorn --host 127.0.0.1 (single worker)."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from mars_agents.agents.model_factory import GeminiConfigurationError, GeminiSettings
from mars_agents.api.presenter import present, present_human, reveal
from mars_agents.api.schemas import (
    ExperimentSnapshot,
    FinalResultsSnapshot,
    GroundTruthSnapshot,
    HealthSnapshot,
    HumanRequestSnapshot,
    HumanResponseInput,
    ReplayResponse,
)
from mars_agents.config import ExperimentConfig
from mars_agents.domain.models import HumanResponse
from mars_agents.experiments.service import ExperimentBusyError, ExperimentService

ROOT = Path(__file__).resolve().parents[4]


def create_app(data_dir: Path | None = None, settings: GeminiSettings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        load_dotenv(ROOT / ".env", override=False)
        root = data_dir or Path(os.environ.get("MARS_DATA_DIR", str(ROOT / "data")))
        if not root.is_absolute():
            root = (ROOT / "backend" / root).resolve()
        service = ExperimentService(root, settings)
        app.state.experiments = service
        try:
            yield
        finally:
            service.close()

    app = FastAPI(title="Mars Water Search", version="1.0.0", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(GeminiConfigurationError)
    async def missing_key(_: Request, error: GeminiConfigurationError):
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.exception_handler(ExperimentBusyError)
    async def busy(_: Request, error: ExperimentBusyError):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(KeyError)
    async def missing(_: Request, error: KeyError):
        return JSONResponse(status_code=404, content={"detail": "Unknown experiment"})

    @app.exception_handler(ValueError)
    async def invalid(_: Request, error: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(error)})

    def service(request: Request) -> ExperimentService:
        return request.app.state.experiments

    Service = Annotated[ExperimentService, Depends(service)]

    @app.get("/api/health", response_model=HealthSnapshot)
    def health(svc: Service):
        key = svc.settings.gemini_api_key
        return HealthSnapshot(
            gemini_configured=bool(key and key.get_secret_value().strip()),
            model=svc.settings.gemini_model,
        )

    @app.get("/api/config", response_model=ExperimentConfig)
    def config():
        return ExperimentConfig()

    @app.post(
        "/api/experiments", response_model=ExperimentSnapshot, response_model_exclude_none=True
    )
    def create(config: ExperimentConfig, svc: Service):
        return present(svc.create(config))

    @app.get(
        "/api/experiments/{experiment_id}",
        response_model=ExperimentSnapshot,
        response_model_exclude_none=True,
    )
    def get(experiment_id: str, svc: Service):
        return present(
            svc.get(experiment_id), awaiting_human=bool(svc.pending(experiment_id)),
            provider_pause=svc.provider_pause(experiment_id),
        )

    @app.post(
        "/api/experiments/{experiment_id}/step",
        response_model=ExperimentSnapshot,
        response_model_exclude_none=True,
    )
    def step(experiment_id: str, svc: Service):
        return present(
            svc.step(experiment_id), awaiting_human=bool(svc.pending(experiment_id)),
            provider_pause=svc.provider_pause(experiment_id),
        )

    @app.post(
        "/api/experiments/{experiment_id}/reset",
        response_model=ExperimentSnapshot,
        response_model_exclude_none=True,
    )
    def reset(experiment_id: str, svc: Service, config: ExperimentConfig | None = None):
        return present(svc.reset(experiment_id, config))

    @app.get(
        "/api/experiments/{experiment_id}/human-requests", response_model=list[HumanRequestSnapshot]
    )
    def requests(experiment_id: str, svc: Service):
        return [present_human(r) for r in svc.pending(experiment_id)]

    @app.post(
        "/api/experiments/{experiment_id}/human-responses",
        response_model=ExperimentSnapshot,
        response_model_exclude_none=True,
    )
    def respond(experiment_id: str, response: HumanResponseInput, svc: Service):
        exp = svc.respond(experiment_id, HumanResponse.model_validate(response.model_dump()))
        return present(exp, awaiting_human=bool(svc.pending(experiment_id)))

    @app.get(
        "/api/experiments/{experiment_id}/replay",
        response_model=ReplayResponse,
        response_model_exclude_none=True,
    )
    def replay(experiment_id: str, svc: Service):
        return ReplayResponse(
            rounds=[present(exp) for exp in svc.replay(experiment_id)]
        )

    @app.get("/api/experiments/{experiment_id}/results", response_model=FinalResultsSnapshot)
    def results(experiment_id: str, svc: Service):
        exp = svc.get(experiment_id)
        if exp.status not in {"success", "failure"}:
            raise HTTPException(409, "The experiment has not finished.")
        snapshot = present(exp)
        return FinalResultsSnapshot(results=snapshot.results or [], winner=snapshot.winner)

    @app.post(
        "/api/experiments/{experiment_id}/reveal-ground-truth", response_model=GroundTruthSnapshot
    )
    def truth(experiment_id: str, svc: Service):
        exp = svc.get(experiment_id)
        if exp.status not in {"success", "failure"}:
            raise HTTPException(403, "Ground truth is available only after the experiment ends.")
        return reveal(exp)

    return app


app = create_app()
