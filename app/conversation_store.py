import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import asyncpg
from elasticsearch import AsyncElasticsearch


logger = logging.getLogger(__name__)

MAX_MESSAGES_HISTORIQUE = 10
ES_INDEX_MESSAGES = "emma_conversations_messages"


class ConversationStore:
    """
    Stockage production des conversations.

    PostgreSQL contient les métadonnées de conversation ainsi que
    le snapshot du dossier.

    Elasticsearch contient les messages de conversation.
    """

    def __init__(
        self,
        pg_pool: asyncpg.Pool,
        es_client: AsyncElasticsearch,
    ):
        self._pg = pg_pool
        self._es = es_client

    async def creer_conversation(
        self,
        ticket_id: str,
        dossier_context: Dict[str, Any],
    ) -> str:
        async with self._pg.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO conversations (ticket_id, dossier_context)
                VALUES ($1, $2)
                RETURNING conversation_id
                """,
                ticket_id,
                json.dumps(dossier_context),
            )

        conversation_id = str(row["conversation_id"])

        logger.info(
            "Conversation creee : %s (ticket %s)",
            conversation_id,
            ticket_id,
        )

        return conversation_id

    async def get_conversation(
        self,
        conversation_id: str,
    ) -> Optional[Dict[str, Any]]:
        async with self._pg.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT conversation_id, ticket_id, dossier_context
                FROM conversations
                WHERE conversation_id = $1
                """,
                conversation_id,
            )

        if row is None:
            return None

        dossier_context = row["dossier_context"]

        if isinstance(dossier_context, str):
            dossier_context = json.loads(dossier_context)

        return {
            "conversation_id": str(row["conversation_id"]),
            "ticket_id": str(row["ticket_id"]),
            "dossier_context": dossier_context,
        }

    async def get_historique_tronque(
        self,
        conversation_id: str,
        limit: int = MAX_MESSAGES_HISTORIQUE,
    ) -> List[Dict[str, str]]:
        resultat = await self._es.search(
            index=ES_INDEX_MESSAGES,
            query={
                "term": {
                    "conversation_id": conversation_id,
                }
            },
            sort=[
                {
                    "timestamp": {
                        "order": "desc",
                    }
                }
            ],
            size=limit,
        )

        hits = resultat["hits"]["hits"]

        messages = [
            {
                "role": hit["_source"]["role"],
                "content": hit["_source"]["content"],
            }
            for hit in reversed(hits)
        ]

        return messages

    async def ajouter_message(
        self,
        conversation_id: str,
        role: str,
        contenu: str,
        ticket_id: Optional[str] = None,
        analyste_id: Optional[str] = None,
    ) -> None:
        await self._es.index(
            index=ES_INDEX_MESSAGES,
            document={
                "conversation_id": conversation_id,
                "ticket_id": ticket_id,
                "role": role,
                "content": contenu,
                "analyste_id": analyste_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        async with self._pg.acquire() as conn:
            await conn.execute(
                """
                UPDATE conversations
                SET last_message_at = NOW()
                WHERE conversation_id = $1
                """,
                conversation_id,
            )

    async def dossier_context(
        self,
        conversation_id: str,
    ) -> Optional[Dict[str, Any]]:
        conversation = await self.get_conversation(
            conversation_id
        )

        if conversation is None:
            return None

        return conversation["dossier_context"]

    async def ajouter_hypothese(
            self,
            conversation_id: str,
            hypothese: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        conv = self._conversations.get(conversation_id)

        if conv is None:
            raise KeyError(
                f"Conversation introuvable : {conversation_id}"
            )

        hypotheses = conv["dossier_context"].get(
            "hypotheses_existantes",
            [],
        )

        hypotheses.append(hypothese)

        conv["dossier_context"]["hypotheses_existantes"] = hypotheses

        return hypotheses

    async def purger_conversations_demo_expirees(
        self,
        max_age_heures: int = 2,
    ) -> int:
        """
        Supprime les conversations de démonstration anciennes.

        Seules les conversations dont le ticket_id commence par
        'DEMO-' sont concernées.

        Les métadonnées sont supprimées de PostgreSQL et les messages
        associés sont supprimés d'Elasticsearch.

        Retourne le nombre de conversations supprimées.
        """

        seuil = datetime.now(timezone.utc) - timedelta(
            hours=max_age_heures
        )

        async with self._pg.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT conversation_id
                FROM conversations
                WHERE ticket_id LIKE 'DEMO-%'
                  AND created_at < $1
                """,
                seuil,
            )

        if not rows:
            return 0

        conversation_ids = [
            str(row["conversation_id"])
            for row in rows
        ]

        for conversation_id in conversation_ids:
            try:
                await self._es.delete_by_query(
                    index=ES_INDEX_MESSAGES,
                    query={
                        "term": {
                            "conversation_id": conversation_id,
                        }
                    },
                    conflicts="proceed",
                )
            except Exception:
                logger.exception(
                    "Erreur lors de la suppression des messages "
                    "Elasticsearch pour la conversation %s",
                    conversation_id,
                )

        async with self._pg.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM conversations
                WHERE ticket_id LIKE 'DEMO-%'
                  AND created_at < $1
                """,
                seuil,
            )

        try:
            nombre_supprime = int(result.split()[-1])
        except (ValueError, IndexError):
            nombre_supprime = len(conversation_ids)

        logger.info(
            "Purge demo : %d conversation(s) supprimee(s)",
            nombre_supprime,
        )

        return nombre_supprime

    async def fermer(self) -> None:
        try:
            await self._es.close()
        except Exception:
            logger.exception(
                "Erreur lors de la fermeture Elasticsearch"
            )

        try:
            await self._pg.close()
        except Exception:
            logger.exception(
                "Erreur lors de la fermeture PostgreSQL"
            )


class InMemoryConversationStore:
    """
    Stockage de secours, en mémoire process.

    ATTENTION : perdu au redémarrage du service, et non partagé entre
    plusieurs instances derrière un load balancer. Utilisé uniquement
    quand PostgreSQL et/ou Elasticsearch ne sont pas configurés ou
    injoignables — pour permettre de développer et tester Emma IA
    sans dépendre des vraies bases. À ne jamais utiliser tel quel en
    production multi-instance.

    Implémente exactement la même interface async que
    ConversationStore ci-dessus, afin que main.py n'ait aucune
    distinction à faire entre les deux.
    """

    def __init__(self):
        self._conversations: Dict[str, Dict[str, Any]] = {}

    async def creer_conversation(
        self,
        ticket_id: str,
        dossier_context: Dict[str, Any],
    ) -> str:
        conversation_id = str(uuid.uuid4())

        self._conversations[conversation_id] = {
            "conversation_id": conversation_id,
            "ticket_id": ticket_id,
            "dossier_context": dossier_context,
            "messages": [],
            "created_at": datetime.now(timezone.utc),
            "last_message_at": datetime.now(timezone.utc),
        }

        logger.info(
            "[MEMOIRE] Conversation creee : %s (ticket %s)",
            conversation_id,
            ticket_id,
        )

        return conversation_id

    async def get_conversation(
        self,
        conversation_id: str,
    ) -> Optional[Dict[str, Any]]:
        conv = self._conversations.get(conversation_id)

        if conv is None:
            return None

        return {
            "conversation_id": conv["conversation_id"],
            "ticket_id": conv["ticket_id"],
            "dossier_context": conv["dossier_context"],
        }

    async def get_historique_tronque(
        self,
        conversation_id: str,
        limit: int = MAX_MESSAGES_HISTORIQUE,
    ) -> List[Dict[str, str]]:
        conv = self._conversations.get(conversation_id)

        if conv is None:
            return []

        messages = conv["messages"]

        return (
            messages[-limit:]
            if len(messages) > limit
            else messages
        )

    async def ajouter_message(
        self,
        conversation_id: str,
        role: str,
        contenu: str,
        ticket_id: Optional[str] = None,
        analyste_id: Optional[str] = None,
    ) -> None:
        conv = self._conversations.get(conversation_id)

        if conv is None:
            raise KeyError(
                f"Conversation introuvable : {conversation_id}"
            )

        conv["messages"].append(
            {
                "role": role,
                "content": contenu,
            }
        )

        conv["last_message_at"] = datetime.now(timezone.utc)

    async def dossier_context(
        self,
        conversation_id: str,
    ) -> Optional[Dict[str, Any]]:
        conv = self._conversations.get(conversation_id)

        return (
            conv["dossier_context"]
            if conv
            else None
        )

    async def ajouter_hypothese(
        self,
        conversation_id: str,
        hypothese: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Ajoute une hypothèse au dossier_context de la conversation.

        Version mémoire de l'opération effectuée par
        ConversationStore, afin de conserver exactement la même
        interface async.

        Retourne la liste complète des hypothèses après ajout.
        """

        conv = self._conversations.get(conversation_id)

        if conv is None:
            raise KeyError(
                f"Conversation introuvable : {conversation_id}"
            )

        dossier_context = conv["dossier_context"]

        if not isinstance(dossier_context, dict):
            dossier_context = {}
            conv["dossier_context"] = dossier_context

        hypotheses = dossier_context.get(
            "hypotheses_existantes",
            [],
        )

        if not isinstance(hypotheses, list):
            hypotheses = []

        hypotheses.append(hypothese)

        dossier_context["hypotheses_existantes"] = hypotheses

        return hypotheses

    async def purger_conversations_demo_expirees(
        self,
        max_age_heures: int = 2,
    ) -> int:
        seuil = datetime.now(timezone.utc) - timedelta(
            hours=max_age_heures
        )

        a_supprimer = [
            conv_id
            for conv_id, conv in self._conversations.items()
            if conv["ticket_id"].startswith("DEMO-")
            and conv["created_at"] < seuil
        ]

        for conv_id in a_supprimer:
            del self._conversations[conv_id]

        if a_supprimer:
            logger.info(
                "[MEMOIRE] Purge demo : %d conversation(s) "
                "supprimee(s)",
                len(a_supprimer),
            )

        return len(a_supprimer)

    async def fermer(self) -> None:
        # Rien à fermer pour la version en mémoire.
        pass


async def creer_conversation_store(
    postgres_dsn: str,
    elasticsearch_url: str,
):
    """
    Initialise le stockage adapté à la configuration disponible.

    Si POSTGRES_DSN ou ELASTICSEARCH_URL sont absents, ou si la
    connexion à l'un ou l'autre échoue, on retombe automatiquement
    sur InMemoryConversationStore plutôt que de bloquer le démarrage
    du service. À remplacer par de vraies valeurs une fois les bases
    créées — aucun autre changement de code ne sera nécessaire.
    """

    if not postgres_dsn or not elasticsearch_url:
        logger.warning(
            "POSTGRES_DSN et/ou ELASTICSEARCH_URL non configures — "
            "utilisation du stockage EN MEMOIRE "
            "(perdu au redemarrage, non partage entre instances). "
            "A remplacer avant tout usage multi-instance ou en "
            "production."
        )

        return InMemoryConversationStore()

    try:
        logger.info(
            "Initialisation du pool PostgreSQL..."
        )

        pg_pool = await asyncpg.create_pool(
            dsn=postgres_dsn
        )

        logger.info(
            "Initialisation du client Elasticsearch..."
        )

        es_client = AsyncElasticsearch(
            hosts=[elasticsearch_url]
        )

        await es_client.info()

        logger.info(
            "Connexion Elasticsearch OK"
        )

        logger.info(
            "ConversationStore production initialise"
        )

        return ConversationStore(
            pg_pool=pg_pool,
            es_client=es_client,
        )

    except Exception:
        logger.exception(
            "Echec de connexion a PostgreSQL/Elasticsearch — "
            "repli automatique sur le stockage EN MEMOIRE"
        )

        return InMemoryConversationStore()


async def fermer_conversation_store(
    store,
) -> None:
    """
    Ferme proprement les connexions du store, quelle que soit son
    implémentation (production ou mémoire).
    """

    if store is None:
        return

    try:
        await store.fermer()

        logger.info(
            "ConversationStore ferme"
        )

    except Exception:
        logger.exception(
            "Erreur lors de la fermeture du ConversationStore"
        )


conversation_store: Optional[ConversationStore] = None
