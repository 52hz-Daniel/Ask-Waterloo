from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_database_url: str = "postgresql+psycopg://navigator_app:local_app_only@db/navigator"
    migration_database_url: str = (
        "postgresql+psycopg://navigator_migrator:local_migrator_only@db/navigator"
    )
    auth_mode: str = "synthetic"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

