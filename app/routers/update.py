from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Header
from sqlalchemy.orm import Session

from app.api_common import fail, get_db, ok, require_user
from app.update_service import check_update_payload, runtime_version_payload, trigger_update_webhook

router = APIRouter()


@router.get("/version")
def version_info():
    return ok(runtime_version_payload())


@router.get("/update/check")
def update_check(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    if user.type != 0:
        return fail("forbidden", 403)
    try:
        return ok(check_update_payload())
    except Exception as exc:
        return fail(f"check update failed: {exc}", 502)


@router.post("/update/trigger")
def update_trigger(payload: dict = Body(default_factory=dict), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    if user.type != 0:
        return fail("forbidden", 403)
    try:
        result = trigger_update_webhook(
            user={
                "userId": user.user_id,
                "email": user.email,
                "name": user.name,
            },
            payload=payload,
        )
        return ok(result)
    except ValueError as exc:
        return fail(str(exc), 400)
    except Exception as exc:
        return fail(f"trigger update failed: {exc}", 502)
