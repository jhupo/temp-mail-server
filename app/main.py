from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api_common import ensure_default_admin, get_setting
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.routers.accounts import router as accounts_router
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.emails import router as emails_router
from app.routers.internal import router as internal_router
from app.routers.settings import router as settings_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_default_admin(db)
        get_setting(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Cloud Mail Python Backend", lifespan=lifespan)


@app.middleware("http")
async def worker_api_compat(request, call_next):
    path = request.scope.get("path", "")
    if path == "/api":
        request.scope["path"] = "/"
    elif path.startswith("/api/"):
        request.scope["path"] = path[4:]
    return await call_next(request)


@app.get("/healthz")
def healthz():
    return {"ok": True}


app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(accounts_router)
app.include_router(emails_router)
app.include_router(admin_router)
app.include_router(internal_router)


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
