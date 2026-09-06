from enum import Enum
from fastapi import Header, HTTPException
from app.config import settings


class ClientType(str, Enum):
    SAAS = "saas"
    DEMO = "demo"


async def verifier_client(
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> ClientType:
    if x_api_key == settings.api_key_saas:
        return ClientType.SAAS

    if x_api_key == settings.api_key_demo:
        return ClientType.DEMO

    raise HTTPException(status_code=401, detail="Clé API invalide")


async def exiger_saas(
    client: ClientType = Header(default=None, alias="X-Client-Type"),
) -> None:
    """
    Pour les routes réservées au SaaS (jamais accessibles à la démo
    publique), par exemple les stats internes ou l'accès aux vrais
    dossiers clients.
    """
    if client != ClientType.SAAS:
        raise HTTPException(
            status_code=403,
            detail="Cette route n'est pas accessible depuis ce client",
        )