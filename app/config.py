from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    database_url: str = Field(default="postgresql+psycopg://cloudmail:cloudmail@tempmail-postgres:5432/cloudmail", alias="DATABASE_URL")
    redis_url: str = Field(default="redis://tempmail-redis:6379/0", alias="REDIS_URL")
    frontend_dist_dir: str = Field(default="mail-vue/dist", alias="FRONTEND_DIST_DIR")
    smtp_gateway_token: str = Field(default="change_me_gateway_token", alias="SMTP_GATEWAY_TOKEN")
    smtp_host: str = Field(default="0.0.0.0", alias="SMTP_HOST")
    smtp_port: int = Field(default=25, alias="SMTP_PORT")
    smtp_api_base: str = Field(default="http://tempmail-api:8000", alias="SMTP_API_BASE")
    smtp_out_host: str = Field(default="", alias="SMTP_OUT_HOST")
    smtp_out_port: int = Field(default=587, alias="SMTP_OUT_PORT")
    smtp_out_username: str = Field(default="", alias="SMTP_OUT_USERNAME")
    smtp_out_password: str = Field(default="", alias="SMTP_OUT_PASSWORD")
    smtp_out_from_email: str = Field(default="", alias="SMTP_OUT_FROM_EMAIL")
    smtp_out_use_tls: bool = Field(default=True, alias="SMTP_OUT_USE_TLS")
    smtp_out_use_ssl: bool = Field(default=False, alias="SMTP_OUT_USE_SSL")
    default_admin_email: str = Field(default="superadmin@jhupo.com", alias="CLOUD_MAIL_ADMIN")
    default_admin_password: str = Field(default="JIang521.", alias="CLOUD_MAIL_ADMIN_PASSWORD")
    default_jwt_secret: str = Field(default="change_me_super_secret", alias="CLOUD_MAIL_JWT_SECRET")
    cloud_mail_domain: str = Field(default="", alias="CLOUD_MAIL_DOMAIN")
    session_prefix: str = Field(default="cloudmail:session:", alias="SESSION_PREFIX")

    @property
    def frontend_dist_path(self) -> Path:
        return Path(self.frontend_dist_dir)


settings = Settings()
