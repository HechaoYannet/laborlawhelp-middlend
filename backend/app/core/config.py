from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://localhost/laborlawhelp"
    redis_url: str = "redis://localhost:6379/0"
    oh_base_url: str = "http://localhost:8080"
    oh_api_key: str = "sk-local"
    oh_default_workflow: str = "labor_consultation"
    app_enable_local_rule_fallback: bool = False
    rate_limit_per_minute: int = 20

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
