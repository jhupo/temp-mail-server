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
        "noRecipient": "no_recipient",
        "r2Domain": "r2_domain",
        "siteKey": "site_key",
        "secretKey": "secret_key",
        "background": "background",
        "loginOpacity": "login_opacity",
        "regKey": "reg_key",
        "addVerifyCount": "add_verify_count",
        "regVerifyCount": "reg_verify_count",
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
        "bucket": "bucket",
        "endpoint": "endpoint",
        "region": "region",
        "s3AccessKey": "s3_access_key",
        "s3SecretKey": "s3_secret_key",
        "forcePathStyle": "force_path_style",
        "storageType": "storage_type",
        "tgBotStatus": "tg_bot_status",
        "tgBotToken": "tg_bot_token",
        "customDomain": "custom_domain",
        "tgChatId": "tg_chat_id",
        "tgMsgFrom": "tg_msg_from",
        "tgMsgText": "tg_msg_text",
        "tgMsgTo": "tg_msg_to",
        "forwardStatus": "forward_status",
        "forwardEmail": "forward_email",
        "ruleType": "rule_type",
        "ruleEmail": "rule_email",
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
    if "resendToken" in payload:
        setting.resend_token = (payload.get("resendToken") or "").strip()
    if "resendTokens" in payload:
        setting.resend_tokens = json.dumps(payload.get("resendTokens") or {})
        tokens = payload.get("resendTokens") or {}
        first_token = next(iter(tokens.values()), "")
        setting.resend_token = first_token
    if "emailPrefixFilter" in payload:
        setting.email_prefix_filter = json.dumps(payload.get("emailPrefixFilter") or [])
    if setting.bucket or setting.endpoint:
        setting.storage_type = "postgres"
    else:
        setting.storage_type = "postgres"
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
