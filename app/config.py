from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "playground123"
    default_gen_model: str = "gemini-2.5-flash"
    default_embed_model: str = "gemini-embedding-001"

    class Config:
        env_file = ".env"


settings = Settings()
