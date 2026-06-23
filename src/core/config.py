from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    #App

    app_name: str = "CMS Platform"
    app_env: str = "development"
    app_debug: bool= True
    secret_key: str
    api_prefix: str = "/api/v1"
    # Storage — S3/MinIO (leave blank to use local disk in dev)
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "ap-south-1"
    s3_endpoint_url: str = ""   # MinIO: http://localhost:9000
    s3_public_url: str = ""     # CDN or MinIO public URL
    # API base URL (used to construct local file URLs)
    api_base_url: str = "http://localhost:8000"
    
    #Database 

    database_url: str
    database_sync_url: str
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    #Redis

    redis_url: str = "redis://localhost:6379/0"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    # Email (SMTP)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@cmsplatform.com"
    smtp_from_name: str = "CMS Platform"

    # App URL (for email links)
    dashboard_url: str = "http://localhost:3000"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v
    
    #First Superadmin
    first_superadmin_email: str = "admin@cms.com"
    first_superadmin_password: str = "StrongPass123!"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"
    

@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


