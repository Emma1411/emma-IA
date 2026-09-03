from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DossierAnalyseRequest(BaseModel):
    """
    Contrat d'entrée réel de l'API /analyser, aligné sur le
    contrat documenté dans le prompt système Emma IA (section 4).

    donnees_dossier reste volontairement typé en Dict[str, Any] plutôt
    que strictement modélisé : la structure interne (revenus, dettes,
    historique_credit, documents...) varie trop selon le contexte pour
    un typage Pydantic rigide, et une divergence de type y a déjà causé
    des pertes de données silencieuses par le passé (ex: taux_remboursement
    en string vs float). La validation de contenu est déléguée aux règles
    du prompt système, pas à Pydantic.
    """

    donnees_dossier: Dict[str, Any] = Field(default_factory=dict)
    metriques_officielles_calculees: Dict[str, Any] = Field(default_factory=dict)
    champs_obligatoires_pour_ce_produit: List[str] = Field(default_factory=list)


class ChatInput(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)