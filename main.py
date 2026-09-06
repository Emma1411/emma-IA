# app/main.py

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.models import (
    DossierAnalyseRequest,
    ChatInput,
    DemarrerConversationRequest,
    DemarrerConversationResponse,
    ChatMessageInput,
    ChatMessageResponse,
)
from app.emma_ia import EmmaIA
import app.conversation_store as conversation_store_module
from app.conversation_store import (
    MAX_MESSAGES_HISTORIQUE,
    creer_conversation_store,
    fermer_conversation_store,
)
from app.config import settings
from app.auth import verifier_client, exiger_saas, ClientType
from app.rate_limit import limiter


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialise les ressources nécessaires au démarrage du service
    et les ferme proprement à l'arrêt.

    PostgreSQL et Elasticsearch sont initialisés une seule fois
    au démarrage de l'application.
    """

    logger.info("Démarrage d'Emma IA...")

    try:
        conversation_store_module.conversation_store = (
            await creer_conversation_store(
                postgres_dsn=settings.postgres_dsn,
                elasticsearch_url=settings.elasticsearch_url,
            )
        )

        logger.info("ConversationStore initialisé")

    except Exception:
        logger.exception(
            "Impossible d'initialiser le ConversationStore "
            "— démarrage bloqué"
        )
        raise

    yield

    logger.info("Arrêt d'Emma IA...")

    if conversation_store_module.conversation_store is not None:
        try:
            await fermer_conversation_store(
                conversation_store_module.conversation_store
            )
            logger.info("ConversationStore fermé")
        except Exception:
            logger.exception(
                "Erreur lors de la fermeture du ConversationStore"
            )
        finally:
            conversation_store_module.conversation_store = None

    logger.info("Emma IA arrêtée")


app = FastAPI(
    title="Emma IA - SecureFinance-RAG",
    version="2.2.0",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    lifespan=lifespan,
)


app.state.limiter = limiter

app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
)


# Seules les applications connues peuvent appeler l'API
# depuis un navigateur.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://tonsaas.vercel.app",
        "https://emma-demo.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Content-Type",
        "X-API-Key",
        "X-Client-Type",
    ],
)


try:
    emma = EmmaIA()
    logger.info("Emma IA initialisée")
except Exception:
    logger.exception(
        "Erreur lors de l'initialisation d'Emma IA"
    )
    emma = None


def get_conversation_store():
    """
    Retourne l'instance active du ConversationStore.

    Une erreur HTTP 503 est retournée si le stockage n'a pas
    été correctement initialisé au démarrage.
    """

    store = conversation_store_module.conversation_store

    if store is None:
        raise HTTPException(
            status_code=503,
            detail="Stockage des conversations indisponible",
        )

    return store


@app.get("/api/v1")
async def root():
    """Retourne l'état général du service."""

    store_available = (
        conversation_store_module.conversation_store is not None
    )

    return {
        "service": "Emma IA",
        "version": "2.2.0",
        "status": (
            "ok"
            if emma and store_available
            else "error"
        ),
    }


@app.get("/api/v1/health")
async def health():
    """Endpoint utilisé pour vérifier que le service est disponible."""

    store_available = (
        conversation_store_module.conversation_store is not None
    )

    if emma and store_available:
        return {
            "status": "healthy"
        }

    return {
        "status": "unavailable"
    }


@app.post("/api/v1/analyser")
@limiter.limit(settings.rate_limit_saas)
async def analyser_dossier(
    request: Request,
    dossier: DossierAnalyseRequest,
    client: ClientType = Depends(verifier_client),
):
    """Analyse un dossier transmis par le client SaaS."""

    if not emma:
        raise HTTPException(
            status_code=503,
            detail="Emma indisponible",
        )

    try:
        return emma.analyser(
            dossier.model_dump()
        )

    except Exception:
        logger.exception(
            "Erreur lors de l'analyse du dossier"
        )

        raise HTTPException(
            status_code=500,
            detail="Erreur interne de l'analyse",
        )


@app.post(
    "/api/v1/conversations",
    response_model=DemarrerConversationResponse,
)
@limiter.limit(settings.rate_limit_saas)
async def demarrer_conversation(
    request: Request,
    payload: DemarrerConversationRequest,
    client: ClientType = Depends(verifier_client),
):
    """Crée une nouvelle conversation associée à un dossier SaaS."""

    if not emma:
        raise HTTPException(
            status_code=503,
            detail="Emma indisponible",
        )

    if client != ClientType.SAAS:
        raise HTTPException(
            status_code=403,
            detail="Route réservée au SaaS",
        )

    if not payload.ticket_id:
        raise HTTPException(
            status_code=422,
            detail="ticket_id est obligatoire pour une conversation SaaS",
        )

    store = get_conversation_store()

    dossier_context = {
        "donnees_dossier": payload.donnees_dossier,
        "metriques_officielles_calculees": (
            payload.metriques_officielles_calculees
        ),
        "champs_obligatoires_pour_ce_produit": (
            payload.champs_obligatoires_pour_ce_produit
        ),
        "hypotheses_existantes": (
            payload.hypotheses_existantes
        ),
    }

    conversation_id = await store.creer_conversation(
        ticket_id=payload.ticket_id,
        dossier_context=dossier_context,
    )

    return DemarrerConversationResponse(
        conversation_id=conversation_id,
        ticket_id=payload.ticket_id,
    )


@app.post(
    "/api/v1/chat",
    response_model=ChatMessageResponse,
)
@limiter.limit(settings.rate_limit_saas)
async def chat_avec_emma(
    request: Request,
    payload: ChatMessageInput,
    client: ClientType = Depends(verifier_client),
):
    """Envoie un message dans une conversation SaaS existante."""

    if not emma:
        raise HTTPException(
            status_code=503,
            detail="Emma indisponible",
        )

    if client != ClientType.SAAS:
        raise HTTPException(
            status_code=403,
            detail="Route réservée au SaaS",
        )

    store = get_conversation_store()

    conv = await store.get_conversation(
        payload.conversation_id
    )

    if conv is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation introuvable",
        )

    historique = await store.get_historique_tronque(
        payload.conversation_id,
        limit=MAX_MESSAGES_HISTORIQUE,
    )

    try:
        reponse = emma.chat_contextualise(
            message=payload.message,
            dossier_context=conv["dossier_context"],
            historique_messages=historique,
        )

    except Exception:
        logger.exception(
            "Erreur lors du traitement du chat"
        )

        raise HTTPException(
            status_code=500,
            detail="Erreur interne du chat",
        )

    await store.ajouter_message(
        conversation_id=payload.conversation_id,
        role="user",
        contenu=payload.message,
        ticket_id=conv["ticket_id"],
    )

    await store.ajouter_message(
        conversation_id=payload.conversation_id,
        role="assistant",
        contenu=reponse,
        ticket_id=conv["ticket_id"],
    )

    return ChatMessageResponse(
        conversation_id=payload.conversation_id,
        reponse=reponse,
    )


@app.post(
    "/api/v1/demo/conversations",
    response_model=DemarrerConversationResponse,
)
@limiter.limit(settings.rate_limit_demo)
async def demarrer_conversation_demo(
    request: Request,
    payload: DemarrerConversationRequest,
    client: ClientType = Depends(verifier_client),
):
    """
    Ouvre une conversation de démonstration à partir du dossier
    fourni par le visiteur.

    Le ticket_id est généré côté serveur avec le préfixe DEMO-
    afin de garder les conversations de démo séparées du SaaS.
    """

    if not emma:
        raise HTTPException(
            status_code=503,
            detail="Emma indisponible",
        )

    if client != ClientType.DEMO:
        raise HTTPException(
            status_code=403,
            detail="Route réservée à la démo",
        )

    store = get_conversation_store()

    # Purge légère des anciennes conversations de démo
    # à chaque nouvelle session.
    try:
        await store.purger_conversations_demo_expirees(
            max_age_heures=2
        )
    except Exception:
        logger.exception(
            "Erreur lors de la purge des conversations de démo"
        )

    if not payload.donnees_dossier:
        raise HTTPException(
            status_code=422,
            detail=(
                "donnees_dossier ne peut pas être vide — "
                "voir le format attendu."
            ),
        )

    dossier_context = {
        "donnees_dossier": payload.donnees_dossier,
        "metriques_officielles_calculees": (
            payload.metriques_officielles_calculees
        ),
        "champs_obligatoires_pour_ce_produit": (
            payload.champs_obligatoires_pour_ce_produit
        ),
        "hypotheses_existantes": (
            payload.hypotheses_existantes
        ),
    }

    ticket_id_demo = (
        f"DEMO-{uuid.uuid4().hex[:8]}"
    )

    conversation_id = await store.creer_conversation(
        ticket_id=ticket_id_demo,
        dossier_context=dossier_context,
    )

    return DemarrerConversationResponse(
        conversation_id=conversation_id,
        ticket_id=ticket_id_demo,
    )


@app.post(
    "/api/v1/demo/chat",
    response_model=ChatMessageResponse,
)
@limiter.limit(settings.rate_limit_demo)
async def chat_demo(
    request: Request,
    payload: ChatMessageInput,
    client: ClientType = Depends(verifier_client),
):
    """Traite un message dans une conversation de démonstration."""

    if not emma:
        raise HTTPException(
            status_code=503,
            detail="Emma indisponible",
        )

    if client != ClientType.DEMO:
        raise HTTPException(
            status_code=403,
            detail="Route réservée à la démo",
        )

    store = get_conversation_store()

    conv = await store.get_conversation(
        payload.conversation_id
    )

    if (
        conv is None
        or not conv["ticket_id"].startswith("DEMO-")
    ):
        raise HTTPException(
            status_code=404,
            detail="Conversation de démo introuvable",
        )

    historique = await store.get_historique_tronque(
        payload.conversation_id,
        limit=MAX_MESSAGES_HISTORIQUE,
    )

    try:
        reponse = emma.chat_contextualise(
            message=payload.message,
            dossier_context=conv["dossier_context"],
            historique_messages=historique,
        )

    except Exception:
        logger.exception(
            "Erreur lors du chat de démo"
        )

        raise HTTPException(
            status_code=500,
            detail="Erreur interne",
        )

    await store.ajouter_message(
        conversation_id=payload.conversation_id,
        role="user",
        contenu=payload.message,
        ticket_id=conv["ticket_id"],
    )

    await store.ajouter_message(
        conversation_id=payload.conversation_id,
        role="assistant",
        contenu=reponse,
        ticket_id=conv["ticket_id"],
    )

    return ChatMessageResponse(
        conversation_id=payload.conversation_id,
        reponse=reponse,
    )


@app.post("/api/v1/demo/analyser")
@limiter.limit(settings.rate_limit_demo)
async def analyser_demo(
    request: Request,
    dossier: DossierAnalyseRequest,
    client: ClientType = Depends(verifier_client),
):
    """
    Équivalent démo de /analyser.

    Permet au visiteur d'envoyer son propre dossier et de recevoir
    directement le JSON d'analyse sans créer de conversation.
    """

    if not emma:
        raise HTTPException(
            status_code=503,
            detail="Emma indisponible",
        )

    if client != ClientType.DEMO:
        raise HTTPException(
            status_code=403,
            detail="Route réservée à la démo",
        )

    try:
        return emma.analyser(
            dossier.model_dump()
        )

    except Exception:
        logger.exception(
            "Erreur lors de l'analyse de démo"
        )

        raise HTTPException(
            status_code=500,
            detail="Erreur interne de l'analyse",
        )


@app.get("/api/v1/stats")
async def get_stats(
    client: ClientType = Depends(verifier_client),
    _=Depends(exiger_saas),
):
    """Retourne les statistiques du service pour le SaaS."""

    if not emma:
        raise HTTPException(
            status_code=503,
            detail="Emma indisponible",
        )

    return emma.get_stats()
