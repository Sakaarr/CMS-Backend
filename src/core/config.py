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
    
    @property
    def is_production(self) -> bool:
        return self.app_env == "development"
    

@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


