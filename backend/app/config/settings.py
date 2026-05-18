try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):
        pass
from functools import lru_cache
import os

from pydantic import Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    dev = "dev"
    stage = "stage"
    prod = "prod"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(os.getenv("ENV_FILE", "../.env"), "../.env.dev", "../.env.stage", "../.env.prod"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_prefix="",
    )


    app_env: AppEnv = Field(default=AppEnv.dev, alias="APP_ENV", description="Application environment (dev/stage/prod)")

    pg_dsn: PostgresDsn | str = Field(default="", alias="PG_DSN", validation_alias="PG_DSN")

    openrouter_api_key: SecretStr = Field(default=SecretStr(""), alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")
    openrouter_model: str = Field(default="", alias="OPENROUTER_MODEL")
    openrouter_http_referer: str = Field(default="", alias="OPENROUTER_HTTP_REFERER")
    openrouter_app_title: str = Field(default="CognitiveBaseAI", alias="OPENROUTER_APP_TITLE")

    neo4j_uri: str = Field(default="", alias="NEO4J_URI")
    neo4j_user: str = Field(default="", alias="NEO4J_USER")
    neo4j_password: SecretStr = Field(default=SecretStr(""), alias="NEO4J_PASSWORD")

    # Qdrant и Redis удалены — фокус только на PostgreSQL и Neo4j.

    hybrid_alpha: float = Field(default=0.15, alias="HYBRID_ALPHA", description="keyword weight")
    hybrid_beta: float = Field(default=0.35, alias="HYBRID_BETA", description="semantic weight")
    hybrid_gamma: float = Field(default=0.20, alias="HYBRID_GAMMA", description="graph weight")
    hybrid_delta: float = Field(default=0.10, alias="HYBRID_DELTA", description="claim_confidence weight")
    hybrid_epsilon: float = Field(default=0.15, alias="HYBRID_EPSILON", description="evidence_strength weight")
    hybrid_zeta: float = Field(default=0.05, alias="HYBRID_ZETA", description="source_reliability weight")
    hybrid_eta: float = Field(default=0.10, alias="HYBRID_ETA", description="contradiction_risk penalty")

    embedding_model_name: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", alias="EMBEDDING_MODEL_NAME")
    embedding_dim: int = Field(default=384, alias="EMBEDDING_DIM")
    embedding_mode: str = Field(default="auto", alias="EMBEDDING_MODE", description="auto | sentence-transformer | deterministic")

    extraction_mode: str = Field(default="hybrid", alias="EXTRACTION_MODE", description="rules | hybrid | llm")
    extraction_llm_on_demo: bool = Field(default=False, alias="EXTRACTION_LLM_ON_DEMO", description="Run LLM extraction on demo corpus bootstrap")
    extraction_llm_timeout: float = Field(default=60.0, alias="EXTRACTION_LLM_TIMEOUT")
    extraction_llm_max_retries: int = Field(default=2, alias="EXTRACTION_LLM_MAX_RETRIES")

    persistence_enabled: bool = Field(default=True, alias="PERSISTENCE_ENABLED")
    persistence_postgres: bool = Field(default=True, alias="PERSISTENCE_POSTGRES")
    persistence_neo4j: bool = Field(default=True, alias="PERSISTENCE_NEO4J")

    prometheus_enabled: bool = Field(default=False, alias="PROMETHEUS_ENABLED")

    cors_allow_origins: str = Field(default="", alias="CORS_ALLOW_ORIGINS")

    admin_api_key: SecretStr = Field(default=SecretStr(""), alias="ADMIN_API_KEY")

    jwt_secret_key: SecretStr = Field(default=SecretStr(""), alias="JWT_SECRET_KEY")
    jwt_access_ttl_seconds: int = Field(default=900, alias="JWT_ACCESS_TTL_SECONDS")
    jwt_refresh_ttl_seconds: int = Field(default=1209600, alias="JWT_REFRESH_TTL_SECONDS")

    bootstrap_admin_email: str = Field(default="", alias="BOOTSTRAP_ADMIN_EMAIL")
    bootstrap_admin_password: SecretStr = Field(default=SecretStr(""), alias="BOOTSTRAP_ADMIN_PASSWORD")

    kb_domain: str = Field(default="", alias="KB_DOMAIN")
    kb_alt_domain: str = Field(default="", alias="KB_ALT_DOMAIN")
    letsencrypt_email: str = Field(default="", alias="LETSENCRYPT_EMAIL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
