from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LaborLawHelp Middlend"
    app_version: str = "0.2.0"

    database_url: str = "postgresql://localhost/laborlawhelp"
    redis_url: str = "redis://localhost:6379/0"
    storage_backend: str = "memory"  # memory / postgres

    oh_base_url: str = "http://localhost:8080"
    oh_stream_path: str = "/api/v1/stream-run"
    oh_api_key: str = "sk-9b68e283d1e5416da3cc2276f72ddf63"
    oh_default_workflow: str = "labor_consultation"
    oh_use_mock: bool = True
    oh_mode: str = "mock"  # mock / library / remote
    oh_lib_model: str = ""
    oh_lib_api_format: str = "openai"
    oh_lib_base_url: str = ""
    oh_lib_api_key: str = ""
    oh_lib_max_turns: int = 20
    oh_lib_cwd: str = ""
    oh_lib_tool_policy: str = "legal_minimal"  # legal_minimal / full
    oh_connect_timeout_sec: float = 5.0
    oh_read_timeout_sec: float = 60.0
    oh_first_chunk_timeout_sec: float = 15.0
    oh_retry_max_attempts: int = 3
    oh_retry_backoff_seconds: str = "1,2,4"
    oh_protocol_error_threshold: int = 20

    auth_mode: str = "anonymous"  # anonymous / jwt
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    app_enable_local_rule_fallback: bool = False
    rate_limit_per_minute: int = 20
    session_lock_timeout_seconds: int = 30
    cors_allow_origins: str = "http://localhost:5000,http://127.0.0.1:5000"
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "*"
    cors_allow_headers: str = "*"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def validate_openharness_settings(self):
        if self.oh_connect_timeout_sec <= 0:
            raise ValueError("oh_connect_timeout_sec must be > 0")
        if self.oh_read_timeout_sec <= 0:
            raise ValueError("oh_read_timeout_sec must be > 0")
        if self.oh_first_chunk_timeout_sec <= 0:
            raise ValueError("oh_first_chunk_timeout_sec must be > 0")
        if self.oh_retry_max_attempts <= 0:
            raise ValueError("oh_retry_max_attempts must be > 0")
        if self.oh_protocol_error_threshold <= 0:
            raise ValueError("oh_protocol_error_threshold must be > 0")

        _ = self.oh_retry_backoff_schedule

        if self.oh_use_mock:
            return self

        if not self.oh_base_url.strip():
            raise ValueError("oh_base_url is required when oh_use_mock=false")
        if not self.oh_stream_path.strip():
            raise ValueError("oh_stream_path is required when oh_use_mock=false")
        if not self.oh_api_key.strip():
            raise ValueError("oh_api_key is required when oh_use_mock=false")

        parsed = urlparse(self.oh_base_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("oh_base_url must use http or https")
        if not self.oh_stream_path.startswith("/"):
            raise ValueError("oh_stream_path must start with '/'")
        return self

    @property
    def oh_retry_backoff_schedule(self) -> tuple[float, ...]:
        values = []
        for raw in self.oh_retry_backoff_seconds.split(","):
            stripped = raw.strip()
            if not stripped:
                continue
            value = float(stripped)
            if value < 0:
                raise ValueError("oh_retry_backoff_seconds values must be >= 0")
            values.append(value)
        if not values:
            raise ValueError("oh_retry_backoff_seconds must contain at least one value")
        return tuple(values)

    @property
    def cors_allow_origins_list(self) -> list[str]:
        return [item.strip() for item in self.cors_allow_origins.split(",") if item.strip()]

    @property
    def cors_allow_methods_list(self) -> list[str]:
        return [item.strip() for item in self.cors_allow_methods.split(",") if item.strip()]

    @property
    def cors_allow_headers_list(self) -> list[str]:
        return [item.strip() for item in self.cors_allow_headers.split(",") if item.strip()]


settings = Settings()
