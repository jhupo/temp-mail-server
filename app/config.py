from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    database_url: str = Field(default="sqlite:////data/cloud-mail.db", alias="DATABASE_URL")
    frontend_dist_dir: str = Field(default="mail-vue/dist", alias="FRONTEND_DIST_DIR")
    smtp_gateway_token: str = Field(default="change_me_gateway_token", alias="SMTP_GATEWAY_TOKEN")
    default_admin_email: str = Field(default="superadmin@jhupo.com", alias="CLOUD_MAIL_ADMIN")
    default_admin_password: str = Field(default="JIang521.", alias="CLOUD_MAIL_ADMIN_PASSWORD")
    default_jwt_secret: str = Field(default="change_me_super_secret", alias="CLOUD_MAIL_JWT_SECRET")
    cloud_mail_domain: str = Field(default="", alias="CLOUD_MAIL_DOMAIN")

    @property
    def frontend_dist_path(self) -> Path:
        return Path(self.frontend_dist_dir)


settings = Settings()
