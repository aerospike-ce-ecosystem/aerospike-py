from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    aerospike_host: str = "127.0.0.1"
    aerospike_port: int = 18710
    aerospike_namespace: str = "test"
    aerospike_set: str = "users"

    # Backpressure — 0 disables the limiter (default)
    max_concurrent_ops: int = 0
    backpressure_timeout_ms: int = 5000

    # Observability
    metrics_enabled: bool = True
    otel_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "sample-fastapi"
    log_level: int = 2  # LOG_LEVEL_INFO

    model_config = {"env_prefix": "APP_"}


settings = Settings()
