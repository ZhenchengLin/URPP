from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    env: str = "development"

    database_url: str = (
        "postgresql+psycopg://urpp:urpp@localhost:5432/urpp"
    )

    llm_provider: str = "openai"
    llm_model: str = ""
    embedding_model: str = ""

    model_config = SettingsConfigDict(
        env_prefix="URPP_",
        env_file=".env",
    )


settings = Settings()
