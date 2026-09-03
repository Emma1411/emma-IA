import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # DeepSeek
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")

    # Service
    host: str = os.getenv("EMMA_HOST", "0.0.0.0")
    port: int = int(os.getenv("EMMA_PORT", "8001"))
    debug: bool = os.getenv("EMMA_DEBUG", "true").lower() == "true"

    # DeepSeek API
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"

    # Limites
    timeout_seconds: int = 120

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()