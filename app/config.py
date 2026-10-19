"""Typed application configuration.

Every environment variable this project reads is declared here — no
scattered os.environ lookups.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "migrated-service"
    port: int = 8000
    database_url: str = ""
    secret_key: str = "change-me"
    cors_origins: list[str] = ["*"]

    @property
    def sqlalchemy_url(self) -> str:
        """
        DATABASE_URL rewritten onto the dialect SQLAlchemy requires.

        The environment may supply a generic "postgres://" or "mysql://"
        URL; SQLAlchemy needs a dialect-qualified scheme. Only the scheme
        is replaced, so credentials, host, port, database and query
        parameters survive untouched.
        """
        url = self.database_url
        if "://" not in url:
            return url
        _, _, rest = url.partition("://")
        return f"postgresql+psycopg://{rest}"


settings = Settings()
