import json
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# Limite la taille des données reçues dans un dossier.
MAX_TAILLE_DONNEES_DOSSIER = 20_000
# Évite les listes anormalement grandes dans une requête.
MAX_ITEMS_LISTE = 50


class Dette(BaseModel):
    type: str
    montant: float
    taux: float
    duree: int
    mensualite: float


class DossierInput(BaseModel):
    """Données d'entrée utilisées par l'ancienne version de l'analyse."""

    client_id: Optional[str] = None
    nom: Optional[str] = None
    profession: Optional[str] = None
    revenu_mensuel: Optional[float] = None
    revenus_autres: Optional[List[Dict]] = None
    dettes: Optional[List[Dict]] = None
    paiements_mensuels: Optional[float] = None
    score_risque: Optional[int] = None
    montant_maximal_admissible: Optional[float] = None
    duree_demandee: Optional[int] = None
    documents: Optional[Dict] = None
    historique_credit: Optional[Dict] = None
    employeur: Optional[Dict] = None
    conformite: Optional[Dict] = None
    observations_analyste: Optional[Dict] = None


class DossierAnalyseRequest(BaseModel):
    """
    Données reçues par l'API /analyser.

    La structure du dossier reste volontairement souple, car elle peut
    varier selon le produit. Les contrôles de taille sont néanmoins faits
    ici afin d'éviter des requêtes trop volumineuses.
    """

    donnees_dossier: Dict[str, Any] = Field(default_factory=dict)

    metriques_officielles_calculees: Dict[str, Any] = Field(
        default_factory=dict
    )

    champs_obligatoires_pour_ce_produit: List[str] = Field(
        default_factory=list,
        max_length=MAX_ITEMS_LISTE,
    )

    @field_validator("donnees_dossier")
    @classmethod
    def limiter_taille_donnees(
        cls,
        v: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Empêche l'envoi d'un dossier trop volumineux."""

        taille = len(json.dumps(v, ensure_ascii=False))

        if taille > MAX_TAILLE_DONNEES_DOSSIER:
            raise ValueError(
                f"donnees_dossier trop volumineux ({taille} caractères, "
                f"maximum {MAX_TAILLE_DONNEES_DOSSIER})"
            )

        return v


class ChatInput(BaseModel):
    """Message envoyé au chat sans conversation existante."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
    )


class DemarrerConversationRequest(BaseModel):
    """
    Informations nécessaires pour démarrer une conversation.

    Le ticket_id est optionnel afin de permettre la création de conversations
    de démonstration qui ne sont pas liées à un vrai dossier client.
    """

    ticket_id: Optional[str] = None

    donnees_dossier: Dict[str, Any] = Field(default_factory=dict)

    metriques_officielles_calculees: Dict[str, Any] = Field(
        default_factory=dict
    )

    champs_obligatoires_pour_ce_produit: List[str] = Field(
        default_factory=list,
        max_length=MAX_ITEMS_LISTE,
    )

    hypotheses_existantes: List[Dict[str, Any]] = Field(
        default_factory=list,
        max_length=MAX_ITEMS_LISTE,
    )

    @field_validator("donnees_dossier")
    @classmethod
    def limiter_taille_donnees(
        cls,
        v: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Empêche l'envoi d'un dossier trop volumineux."""

        taille = len(json.dumps(v, ensure_ascii=False))

        if taille > MAX_TAILLE_DONNEES_DOSSIER:
            raise ValueError(
                f"donnees_dossier trop volumineux ({taille} caractères, "
                f"maximum {MAX_TAILLE_DONNEES_DOSSIER})"
            )

        return v


class DemarrerConversationResponse(BaseModel):
    """Réponse retournée après la création d'une conversation."""

    conversation_id: str
    ticket_id: str


class ChatMessageInput(BaseModel):
    """Message envoyé dans une conversation existante."""

    conversation_id: str = Field(
        ...,
        min_length=1,
    )

    # Limite volontairement plus basse pour éviter les messages trop longs.
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
    )


class ChatEnvelope(BaseModel):
    type: str
    message: str
    position: Optional[str] = None
    niveau_confiance: Optional[str] = None
    elements_favorables: List[str] = Field(default_factory=list)
    points_attention: List[str] = Field(default_factory=list)
    validation_humaine_requise: List[str] = Field(default_factory=list)


class ChatMessageResponse(BaseModel):
    """Réponse du chat associée à la conversation."""

    conversation_id: str
    mode: Literal["chat", "analyse_complete"]
    reponse: Dict[str, Any]


class AjouterHypotheseRequest(BaseModel):
    """
    Ajoute une hypothèse non vérifiée au dossier d'une conversation
    en cours. Cette hypothèse sera reportée dans toute analyse
    complète générée ensuite via le chat ou /analyser.
    """

    description: str = Field(
        ...,
        min_length=1,
        max_length=1000,
    )

    champ_impacte: Optional[str] = None


class AjouterHypotheseResponse(BaseModel):
    conversation_id: str
    hypotheses_existantes: List[Dict[str, Any]]
