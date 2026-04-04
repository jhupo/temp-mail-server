from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class MailboxNewRequest(BaseModel):
    domain: str | None = Field(default=None, description="e.g. jhupo.com or temp.jhupo.com")
    local_part: str | None = Field(default=None, description="optional custom local part")
    ttl_minutes: int | None = Field(default=None, ge=1, le=24 * 60)


class MailboxNewResponse(BaseModel):
    address: EmailStr
    token: str
    expires_at: datetime


class MessageOut(BaseModel):
    from_addr: str | None
    subject: str | None
    text_body: str | None
    html_body: str | None
    raw_headers: str | None
    received_at: datetime


class MailboxLatestResponse(BaseModel):
    address: EmailStr
    latest: MessageOut | None


class MailboxCodeResponse(BaseModel):
    address: EmailStr
    code: str | None
    received_at: datetime | None
