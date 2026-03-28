from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', case_sensitive=False, extra='ignore')

    wp_url: str = Field(default='')
    wp_user: str = Field(default='')
    wp_app_pass: str = Field(default='')

    postgres_host: str = Field(default='localhost')
    postgres_port: int = Field(default=5434)
    postgres_db: str = Field(default='newsroom_v3')
    postgres_user: str = Field(default='newsroom')
    postgres_password: str = Field(default='newsroom_dev_2026')

    redis_url: str = Field(default='redis://localhost:6381/0')
    kafka_bootstrap_servers: str = Field(default='localhost:9092')

    openai_api_key: str = Field(default='')
    anthropic_api_key: str = Field(default='')
    google_api_key: str = Field(default='')
    xai_api_key: str = Field(default='')
    perplexity_api_key: str = Field(default='')
    deepseek_api_key: str = Field(default='')
    alibaba_api_key: str = Field(default='')

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
