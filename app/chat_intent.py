import re

# Mots-clés qui déclenchent une analyse complète plutôt qu'une
# réponse conversationnelle. Volontairement simple et explicite —
# on préfère un faux négatif occasionnel (l'analyste reformule)
# à une détection floue et imprévisible.
_MOTS_DECLENCHEURS = [
    r"\banalyse\b.*\bdossier\b",
    r"\banalyser\b.*\bdossier\b",
    r"\banalyse\s+compl[eè]te?\b",
    r"\banalyse\s+compl[eè]tement\b",
    r"\brapport\s+complet\b",
    r"\brapport\s+d[ée]taill[eé]\b",
    r"\bfais\b.*\banalyse\b",
    r"\bfais[-\s]moi\b.*\banalyse\b",
    r"\bd[eé]tails?\s+du\s+dossier\b",
    r"\banalyse\s+(?:tout|compl[eè]te?|totale)\b",
    r"\b(?:donne|donnez)[-\s]moi\b.*\b(?:avis|analyse)\b.*\bcompl[eè]t[e]?\b",
    r"\b[eé]value(?:r)?\s+(?:le\s+)?profil\b",
    r"\b[eé]value(?:r)?\s+(?:mon\s+|le\s+)?dossier\b",
    r"\br[eé]sum[eé](?:r)?\s+tout\b",
]


_PATTERN = re.compile("|".join(_MOTS_DECLENCHEURS), re.IGNORECASE)


def est_demande_analyse_complete(message: str) -> bool:
    return bool(_PATTERN.search(message or ""))