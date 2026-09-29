import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from app.models import (
    DossierAnalyseRequest,
    ChatInput,
    DemarrerConversationRequest,
    DemarrerConversationResponse,
    ChatMessageInput,
    ChatMessageResponse,
    AjouterHypotheseRequest,
    AjouterHypotheseResponse,
    ChatDemoRequest,
    ChatDemoResponse,
)
from app.chat_intent import est_demande_analyse_complete
from app.emma_ia import EmmaIA
import app.conversation_store as conversation_store_module
from app.conversation_store import (
    MAX_MESSAGES_HISTORIQUE,
    creer_conversation_store,
    fermer_conversation_store,
)
from app.config import settings
from app.auth import verifier_client, exiger_saas, ClientType


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):

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
    store = conversation_store_module.conversation_store

    if store is None:
        raise HTTPException(
            status_code=503,
            detail="Stockage des conversations indisponible",
        )

    return store


@app.get("/api/v1")
async def root():
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
async def analyser_dossier(
    request: Request,
    dossier: DossierAnalyseRequest,
    client: ClientType = Depends(verifier_client),
):
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
async def demarrer_conversation(
    request: Request,
    payload: DemarrerConversationRequest,
    client: ClientType = Depends(verifier_client),
):
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


async def _traiter_message_chat(
    payload: ChatMessageInput,
    conv: Dict[str, Any],
) -> ChatMessageResponse:
    dossier_context = conv["dossier_context"]
    store = get_conversation_store()

    if est_demande_analyse_complete(payload.message):
        try:
            resultat_complet = emma.analyser(
                {
                    **dossier_context.get(
                        "donnees_dossier",
                        {},
                    ),
                    "metriques_officielles_calculees": (
                        dossier_context.get(
                            "metriques_officielles_calculees",
                            {},
                        )
                    ),
                    "champs_obligatoires_pour_ce_produit": (
                        dossier_context.get(
                            "champs_obligatoires_pour_ce_produit",
                            [],
                        )
                    ),
                    "hypotheses_deja_ajoutees": (
                        dossier_context.get(
                            "hypotheses_existantes",
                            [],
                        )
                    ),
                }
            )

        except Exception:
            logger.exception(
                "Erreur lors de l'analyse complète via chat"
            )

            raise HTTPException(
                status_code=500,
                detail="Erreur interne de l'analyse",
            )

        await store.ajouter_message(
            conversation_id=payload.conversation_id,
            role="user",
            contenu=payload.message,
            ticket_id=conv["ticket_id"],
        )

        synthese = resultat_complet.get(
            "synthese",
            {},
        )

        if isinstance(synthese, dict):
            contenu_assistant = synthese.get(
                "texte",
                "Analyse complète générée.",
            )
        else:
            contenu_assistant = "Analyse complète générée."

        await store.ajouter_message(
            conversation_id=payload.conversation_id,
            role="assistant",
            contenu=contenu_assistant,
            ticket_id=conv["ticket_id"],
        )

        return ChatMessageResponse(
            conversation_id=payload.conversation_id,
            mode="analyse_complete",
            reponse=resultat_complet,
        )

    historique = await store.get_historique_tronque(
        payload.conversation_id,
        limit=MAX_MESSAGES_HISTORIQUE,
    )

    try:
        enveloppe = emma.chat_contextualise(
            message=payload.message,
            dossier_context=dossier_context,
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
        contenu=enveloppe["message"],
        ticket_id=conv["ticket_id"],
    )

    return ChatMessageResponse(
        conversation_id=payload.conversation_id,
        mode="chat",
        reponse=enveloppe,
    )


@app.post(
    "/api/v1/chat",
    response_model=ChatMessageResponse,
)
async def chat_avec_emma(
    request: Request,
    payload: ChatMessageInput,
    client: ClientType = Depends(verifier_client),
):
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

    return await _traiter_message_chat(
        payload=payload,
        conv=conv,
    )


@app.post(
    "/api/v1/conversations/{conversation_id}/hypotheses",
    response_model=AjouterHypotheseResponse,
)
async def ajouter_hypothese_saas(
    request: Request,
    conversation_id: str,
    payload: AjouterHypotheseRequest,
    client: ClientType = Depends(verifier_client),
):
    if client != ClientType.SAAS:
        raise HTTPException(
            status_code=403,
            detail="Route réservée au SaaS",
        )

    store = get_conversation_store()

    conv = await store.get_conversation(
        conversation_id
    )

    if conv is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation introuvable",
        )

    hypothese = {
        "description": payload.description,
        "champ_impacte": payload.champ_impacte,
        "source": "Analyste",
    }

    try:
        hypotheses = await store.ajouter_hypothese(
            conversation_id,
            hypothese,
        )

    except KeyError:
        raise HTTPException(
            status_code=404,
            detail="Conversation introuvable",
        )

    return AjouterHypotheseResponse(
        conversation_id=conversation_id,
        hypotheses_existantes=hypotheses,
    )


@app.post(
    "/api/v1/demo/chat",
    response_model=ChatDemoResponse,
)
async def chat_demo(
    request: Request,
    payload: ChatDemoRequest,
    client: ClientType = Depends(verifier_client),
):
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

    *historique, dernier = payload.messages

    historique_dicts = [
        message.model_dump()
        for message in historique
    ]

    if est_demande_analyse_complete(dernier.content):
        try:
            resultat = emma.analyser(
                {
                    **payload.donnees_dossier,
                    "metriques_officielles_calculees": (
                        payload.metriques_officielles_calculees
                    ),
                    "champs_obligatoires_pour_ce_produit": (
                        payload.champs_obligatoires_pour_ce_produit
                    ),
                    "hypotheses_deja_ajoutees": (
                        payload.hypotheses_existantes
                    ),
                }
            )

            return ChatDemoResponse(
                mode="analyse_complete",
                reponse=resultat,
            )

        except Exception:
            logger.exception(
                "Erreur lors de l'analyse complète démo"
            )

            raise HTTPException(
                status_code=500,
                detail="Erreur interne de l'analyse",
            )

    try:
        enveloppe = emma.chat_contextualise(
            message=dernier.content,
            dossier_context=dossier_context,
            historique_messages=historique_dicts,
        )

        return ChatDemoResponse(
            mode="chat",
            reponse=enveloppe,
        )

    except Exception:
        logger.exception(
            "Erreur lors du chat démo"
        )

        raise HTTPException(
            status_code=500,
            detail="Erreur interne du chat",
        )


@app.post("/api/v1/demo/analyser")
async def analyser_demo(
    request: Request,
    dossier: DossierAnalyseRequest,
    client: ClientType = Depends(verifier_client),
):
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
    if not emma:
        raise HTTPException(
            status_code=503,
            detail="Emma indisponible",
        )

    return emma.get_stats()