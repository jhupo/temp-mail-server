from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends, Header
from sqlalchemy.orm import Session

from app.api_common import get_db, get_setting, ok, require_user, setting_payload
from app.domain_utils import split_domains

router = APIRouter()


@router.get("/setting/query")
@router.get("/setting/websiteConfig")
def setting_query(db: Session = Depends(get_db)):
    return ok(setting_payload(get_setting(db)))


@router.put("/setting/set")
def setting_set(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    setting = get_setting(db)
    field_map = {
        "title": "title",
        "register": "register",
        "receive": "receive",
        "manyEmail": "many_email",
        "addEmail": "add_email",
        "autoRefresh": "auto_refresh",
        "send": "send",
        "r2Domain": "r2_domain",
        "background": "background",
        "loginOpacity": "login_opacity",
        "regKey": "reg_key",
        "noticeTitle": "notice_title",
        "noticeContent": "notice_content",
        "noticeType": "notice_type",
        "noticeDuration": "notice_duration",
        "noticePosition": "notice_position",
        "noticeWidth": "notice_width",
        "noticeOffset": "notice_offset",
        "notice": "notice",
        "loginDomain": "login_domain",
        "minEmailPrefix": "min_email_prefix",
        "projectLink": "project_link",
    }
    for key, attr in field_map.items():
        if key in payload:
            value = payload[key]
            if key == "loginOpacity":
                value = int(float(value) * 100)
            setattr(setting, attr, value)
    if "allowedDomains" in payload:
        setting.allowed_domains = json.dumps(split_domains(payload["allowedDomains"]))
    db.commit()
    db.refresh(setting)
    return ok(setting_payload(setting))


@router.put("/setting/setBackground")
def setting_set_background(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    setting = get_setting(db)
    setting.background = payload.get("background") or ""
    db.commit()
    return ok(setting.background)


@router.delete("/setting/deleteBackground")
def setting_delete_background(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    setting = get_setting(db)
    setting.background = ""
    db.commit()
    return ok()
