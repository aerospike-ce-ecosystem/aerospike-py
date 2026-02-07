from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    aerospike_host: str = "127.0.0.1"
    aerospike_port: int = 3000
    aerospike_namespace: str = "test"
    aerospike_set: str = "users"

    model_config = {"env_prefix": "APP_"}


settings = Settings()
