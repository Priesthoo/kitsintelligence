from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, field_validator
from functools import lru_cache
from __future__ import annotations
from typing import Any, Literal, Union
from pydantic_settings import BaseSettings,SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf",
        case_sensitive= False,
        extra="ignore"
    )
    
    
    #Application
    APP_NAME : str = "Kitsintelligence"
    APP_VERSION : str ="1.0.0"
    ENVIRONMENT : Literal["development","staging","production", "test"] = "development"
    DEBUG : bool = False
    API_V1_PREFIX : str = "/api/v1" 
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS : int = 4
    SECRET_KEY : str = Field(min_length=32, default="CHANGE_NAME_IN_PRODUCTION_012345678910")  
    TIMEZONE : str ="UTC"



#CORS
    CORS_ORIGINS : list[str| None] = [""]
    CORS_ALLOW_CREDENTIALS : bool = True

    POSTGRES_USER : str|None = "" # please it should not be none, i kept it there because i have not configured the database and it should not be union
    POSTGRES_PASSWORD : str| None = "" # same here
    POSTGRES_HOST : str = "localhost"
    POSTGRES_PORT : int = 5432
    POSTGRES_DB : str| None = "" # same here
    DB_POOL_SIZE : int = 20
    DB_MAX_OVERFLOW : int = 10
    DB_POOL_TIMEOUT : int = 30
    DB_POOL_RECYCLE : int = 1800
    DB_ECHO : bool = False

    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
           return( f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
               )

    @property
    def SQLALCHEMY_SYNC_DATABASE_URI(self) -> str :
        return NotImplementedError()

# Redis

    REDIS_HOST : str = "localhost"
    REDIS_PORT : int = 6379
    REDIS_DB : int = 0
    REDIS_PASSWORD :str|None = None
    REDIS_MAX_CONNECTIONS : int = 100
    CACHE_DEFAULT_TTL_SECONDS : int = 300

#Celery 
    CELERY_BROKER_URL : str|None = "" #it should not be none 
    CELERY_RESULT_BACKEND : str| None = "" #alos here i made it none because i have not configured it in the setting
    CELERY_TASK_ALWAYS_EAGER : bool = False


# JWT / Security
    JWT_ALGORITHM : str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES : int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS : int = 14
    JWT_ISSUERS : str = "kitsintelligence"
    PASSWORD_MIN_LENGTH : int = 10
    API_KEY_PREFIX : str = "kits"
    MFA_ISSUER_NAME : str = "kitsintelligence"


#Rate-limiting
    RATE_LIMIT_REQUESTS : int = 100
    RATE_LIMITS_WINDOW_SECONDS : int = 60


# object storage (s3 - compatible)
    S3_ENDPOINT_URL : str|None = None
    S3_ACCESS_KEY : str = ""
    S3_SECRET_KEY : str = ""
    S3_BUCKET : str = ""
    S3_REGION : str = ""
    S3_USE_SSL : bool = False


#AI Providers
    ANTHROPIC_API_KEY :str| None = None
    AI_DEFAULT_MODEL : str = "claude-sonnet-4-6"
    AI_MAX_TOKENS : int = 4096
    AI_REQUEST_TIMEOUT_SECONDS : int = 60 


#Observability 
    LOG_LEVEL : str = "INFO"
    LOG_JSON : bool = True
    OTEL_EXPORTER_OTLP_ENDPOINT :str | None = None
    OTEL_SERVICE_NAME : str = "kitsintelligence-api"
    PROMETHEUS_METRICS_PATH : str = "/metrics"
    SENTRY_DSN :str | None = None


#Scheduler
    HYDRATION_DEFAULT_INTERVAL_SECONDS : int = 300
    HYDRATION_MAX_CONCURRENT_JOBS : int = 20
    CONNECTOR_REQUEST_TIMEOUT_SECONDS : int = 30
    CONNECTOR_MAX_RETRIES : int = 3
    CONNECTOR_RETRY_BACKOFF_SECONDS : int = 5

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls,v:Any) -> Any :
     if isinstance(v,str):
        return [origin.strip() for origin in v.split("") if origin.strip()]
     return v

    @property
    def is_production(self) -> bool :
     return self.ENVIRONMENT == "production"

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
 
