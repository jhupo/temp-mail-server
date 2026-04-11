from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import IncomingEmail


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Cloud Mail VPS Python Backend", lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/internal/smtp/receive")
def internal_smtp_receive(
    payload: dict,
    smtp_gateway_token: str | None = Header(default=None, alias="x-smtp-gateway-token"),
):
    if smtp_gateway_token != settings.smtp_gateway_token:
        raise HTTPException(status_code=403, detail="invalid smtp gateway token")

    recipients = payload.get("to") or []
    if not isinstance(recipients, list) or not recipients:
        raise HTTPException(status_code=400, detail="no recipients")

    db = SessionLocal()
    try:
        for recipient in recipients:
            db.add(
                IncomingEmail(
                    mail_from=payload.get("from"),
                    rcpt_to=recipient,
                    subject=payload.get("subject"),
                    text_body=payload.get("text"),
                    html_body=payload.get("html"),
                    raw_body=payload.get("raw"),
                )
            )
        db.commit()
    finally:
        db.close()
    return {"ok": True}


frontend_dist = settings.frontend_dist_path
frontend_index = frontend_dist / "index.html"
if frontend_dist.exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def frontend_root():
        if frontend_index.exists():
            return FileResponse(frontend_index)
        raise HTTPException(status_code=404, detail="frontend not built")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend_spa(full_path: str):
        requested = frontend_dist / full_path
        if requested.exists() and requested.is_file():
            return FileResponse(requested)
        if frontend_index.exists():
            return FileResponse(frontend_index)
        raise HTTPException(status_code=404, detail="frontend not built")
