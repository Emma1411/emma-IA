import re

# Mots-clés qui déclenchent une analyse complète plutôt qu'une
# réponse conversationnelle. Volontairement simple et explicite —
# on préfère un faux négatif occasionnel (l'analyste reformule)
# à une détection floue et imprévisible.
_MOTS_DECLENCHEURS = [
    r"\banalyse\b.*\bdossier\b",
    r"\banalyser\b.*\bdossier\b",
    r"\banalyse\s+complet",
    r"\bfais\b.*\banalyse\b",
    r"\brapport\s+complet\b",
    r"\bdétails?\s+du\s+dossier\b",
]

_PATTERN = re.compile("|".join(_MOTS_DECLENCHEURS), re.IGNORECASE)


def est_demande_analyse_complete(message: str) -> bool:
    """
    Détecte si le message de l'analyste demande une analyse complète
    du dossier plutôt qu'une réponse conversationnelle ponctuelle.

    Volontairement basé sur des règles explicites (pas sur le LLM)
    pour garder un comportement prévisible et testable — cohérent
    avec le principe du projet : jamais laisser le modèle décider
    seul d'un format de sortie critique.
    """
    return bool(_PATTERN.search(message or ""))