from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LaborLawHelp Middlend"
    app_version: str = "0.2.0"

    database_url: str = "postgresql://localhost/laborlawhelp"
    redis_url: str = "redis://localhost:6379/0"
    storage_backend: str = "memory"  # memory / postgres

    oh_base_url: str = "http://localhost:8080"
    oh_stream_path: str = "/api/v1/stream-run"
    oh_api_key: str = "sk-local"
    oh_default_workflow: str = "labor_consultation"
    oh_use_mock: bool = True

    auth_mode: str = "anonymous"  # anonymous / jwt
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    app_enable_local_rule_fallback: bool = False
    rate_limit_per_minute: int = 20
    session_lock_timeout_seconds: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
