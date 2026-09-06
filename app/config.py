import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv


load_dotenv()


class Settings(BaseSettings):
    # Configuration du service
    host: str = os.getenv("EMMA_HOST", "0.0.0.0")
    port: int = int(os.getenv("EMMA_PORT", "8001"))
    debug: bool = os.getenv("EMMA_DEBUG", "true").lower() == "true"

    # Configuration DeepSeek
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"

    # Connexions aux services externes
    postgres_dsn: str = ""
    elasticsearch_url: str = ""

    # Clés API par client autorisé
    # Chaque client doit avoir sa propre clé.
    api_key_saas: str
    api_key_demo: str

    # Limites anti-abus
    # La démo publique est volontairement plus limitée.
    rate_limit_demo: str = "10/minute"
    rate_limit_saas: str = "60/minute"

    # Délai maximum pour les appels externes
    timeout_seconds: int = 120

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
