from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
import sys


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = Field(default="sqlite:///./temp_mail.db", alias="DATABASE_URL")
    allowed_root_domain: str = Field(default="", alias="ALLOWED_ROOT_DOMAIN")
    allowed_root_domains: str | None = Field(default=None, alias="ALLOWED_ROOT_DOMAINS")
    smtp_host: str = Field(default="0.0.0.0", alias="SMTP_HOST")
    smtp_port: int = Field(default=25, alias="SMTP_PORT")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    mailbox_default_ttl_minutes: int = Field(default=60, alias="MAILBOX_DEFAULT_TTL_MINUTES")
    max_body_chars: int = Field(default=100_000, alias="MAX_BODY_CHARS")
    allow_auto_create_on_smtp: bool = Field(default=True, alias="ALLOW_AUTO_CREATE_ON_SMTP")
    api_master_key: str | None = Field(default=None, alias="API_MASTER_KEY")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    rate_limit_new_per_minute: int = Field(default=30, alias="RATE_LIMIT_NEW_PER_MINUTE")
    cleanup_interval_seconds: int = Field(default=60, alias="CLEANUP_INTERVAL_SECONDS")
    frontend_dist_dir: str = Field(default="frontend/dist", alias="FRONTEND_DIST_DIR")
    object_storage_dir: str = Field(default="storage/objects", alias="OBJECT_STORAGE_DIR")
    certbot_webroot_dir: str = Field(default="storage/certbot-webroot", alias="CERTBOT_WEBROOT_DIR")
    certbot_scripts_dir: str = Field(default="deploy/certbot", alias="CERTBOT_SCRIPTS_DIR")
    certbot_reload_command: str = Field(default="nginx -s reload", alias="CERTBOT_RELOAD_COMMAND")
    cert_renew_check_seconds: int = Field(default=43200, alias="CERT_RENEW_CHECK_SECONDS")
    update_branch: str = Field(default="master", alias="UPDATE_BRANCH")
    update_remote: str = Field(default="origin", alias="UPDATE_REMOTE")
    update_reload_command: str = Field(default="", alias="UPDATE_RELOAD_COMMAND")

    @property
    def allowed_domains(self) -> list[str]:
        raw_values: list[str] = []
        if self.allowed_root_domains:
            raw_values.extend(self.allowed_root_domains.split(","))
        elif self.allowed_root_domain:
            raw_values.append(self.allowed_root_domain)

        domains: list[str] = []
        for value in raw_values:
            domain = value.strip().lower()
            if domain and domain not in domains:
                domains.append(domain)
        return domains

    @property
    def primary_domain(self) -> str:
        domains = self.allowed_domains
        if domains:
            return domains[0]
        return self.allowed_root_domain.lower().strip()

    @property
    def frontend_dist_path(self) -> Path:
        return Path(self.frontend_dist_dir)

    @property
    def object_storage_path(self) -> Path:
        return Path(self.object_storage_dir)

    @property
    def certbot_webroot_path(self) -> Path:
        return Path(self.certbot_webroot_dir)

    @property
    def certbot_scripts_path(self) -> Path:
        return Path(self.certbot_scripts_dir)

    @property
    def repo_root_path(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def python_executable(self) -> str:
        return sys.executable


settings = Settings()
