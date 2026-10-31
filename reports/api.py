import asyncio
import secrets
import tomllib
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from temporalio.service import RPCError, RPCStatusCode

from reports.config import Settings, connect_temporal
from reports.models import ReportInput, ReportJob
from reports.store import Store
from reports.workflows import ReportWorkflow

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def create_app(settings=None, store=None, temporal=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = settings or Settings.from_env()
        app.state.store = store or Store(app.state.settings.database_url)
        app.state.temporal = temporal or await connect_temporal(app.state.settings)
        yield

    app = FastAPI(title="Report example", lifespan=lifespan)
    project = tomllib.loads(PYPROJECT.read_text())["project"]
    package = {"name": project["name"], "version": project["version"]}
    bearer = HTTPBearer(auto_error=False)
    app.mount(
        "/ui", StaticFiles(directory=Path(__file__).parent / "ui", html=True), name="ui"
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo raw inputs (including non-finite JSON numbers) into errors.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {key: error[key] for key in ("loc", "msg", "type")}
                    for error in exc.errors()
                ]
            },
        )

    async def authorize(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ):
        token = app.state.settings.api_token
        if token and (
            credentials is None
            or not secrets.compare_digest(
                credentials.credentials.encode(), token.encode()
            )
        ):
            raise HTTPException(401, "Invalid API token")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/version")
    async def version():
        return package

    @app.get("/ready")
    async def ready():
        try:
            async with asyncio.timeout(8):
                await app.state.store.ready()
                if not await app.state.temporal.service_client.check_health():
                    raise RuntimeError("Temporal is not healthy")
        except Exception:
            raise HTTPException(503, "Dependencies unavailable") from None
        return {"status": "ready"}

    @app.get("/", dependencies=[Depends(authorize)])
    async def index():
        return {
            "service": "Report example",
            "environment": app.state.settings.environment,
            "usage": "POST /reports with values and optional delay_seconds",
        }

    @app.post("/reports", status_code=202, dependencies=[Depends(authorize)])
    async def submit(body: ReportInput):
        report_id = str(uuid4())
        try:
            async with asyncio.timeout(10):
                await app.state.temporal.start_workflow(
                    ReportWorkflow.run,
                    ReportJob(report_id, body.values, body.delay_seconds),
                    id=f"report-{report_id}",
                    task_queue=app.state.settings.task_queue,
                    execution_timeout=timedelta(hours=1),
                )
        except Exception:
            raise HTTPException(503, "Could not confirm report acceptance") from None
        return {"id": report_id, "status": "queued", "url": f"/reports/{report_id}"}

    @app.get("/reports", dependencies=[Depends(authorize)])
    async def list_reports(limit: int = Query(default=20, ge=1, le=100)):
        try:
            async with asyncio.timeout(10):
                return {"items": await app.state.store.latest(limit)}
        except Exception:
            raise HTTPException(503, "Report listing unavailable") from None

    @app.get("/reports/{report_id}", dependencies=[Depends(authorize)])
    async def get_report(report_id: UUID):
        try:
            async with asyncio.timeout(10):
                report = await app.state.store.get(str(report_id))
                if report and report["status"] == "completed":
                    return report
                description = await app.state.temporal.get_workflow_handle(
                    f"report-{report_id}"
                ).describe()
                status = description.status.name.lower()
                return {"id": str(report_id), "status": status, "report": report}
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                raise HTTPException(404, "Report not found") from None
            raise HTTPException(503, "Temporal unavailable") from None
        except Exception:
            raise HTTPException(503, "Report lookup unavailable") from None

    return app


app = create_app()
