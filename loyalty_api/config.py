from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Ithute Loyalty Engine"
    environment: str = "development"
    ledger_internal_url: str = ""
    ledger_internal_key: str = ""
    ledger_key_id: str = ""
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    database_url: str = "postgresql+asyncpg://loyalty:loyalty@localhost:5432/loyalty"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
