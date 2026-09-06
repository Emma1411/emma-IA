# Emma IA — Service d'Analyse de Crédit

Service backend d'analyse de crédit utilisant l'intelligence artificielle pour extraire, structurer et analyser des dossiers financiers, puis générer des synthèses et des recommandations. Emma IA est un outil d'**assistance à la décision**, jamais un système de décision autonome — chaque appréciation qu'elle produit reste soumise à validation humaine.

---

## Fonctionnalités

- Analyse automatisée de dossiers de crédit à partir de données structurées
- Extraction et structuration des données financières (revenus, dettes, historique de crédit, paramètres de la demande)
- Interprétation des métriques officielles calculées en amont par le moteur de règles (ratio d'endettement, capacité de remboursement, score de risque, montant maximal admissible) — jamais recalculées par Emma elle-même
- Détection de patterns factuels (historique de crédit, tendances de revenu, incohérences documentaires)
- Génération de synthèses et d'appréciations analytiques traçables
- Mode conversationnel avec mémoire (une conversation reste toujours ancrée sur un seul dossier)
- Gestion des hypothèses non vérifiées ajoutées par l'analyste en cours de conversation, reportées automatiquement dans toute analyse complète ultérieure
- Deux surfaces d'accès distinctes : API SaaS (authentifiée, liée aux vrais dossiers clients) et API de démonstration publique (isolée, dossiers fournis par le visiteur)
- Traçabilité complète : chaque affirmation d'Emma est reliée à une donnée fournie, une métrique officielle, ou une information explicitement identifiée comme non vérifiée

---

## Stack technique

- Python 3.11
- FastAPI
- DeepSeek (moteur d'inférence LLM, via le SDK OpenAI)
- Pydantic (validation stricte des schémas d'entrée/sortie)
- Uvicorn / Gunicorn
- PostgreSQL (métadonnées de conversation — voir section Persistance)
- Elasticsearch (historique des messages — voir section Persistance)
- slowapi (rate limiting)
- Docker / Docker Compose
- OpenAPI / Swagger

---

## Architecture

```
Client (SaaS ou Démo)
        │
        ▼
   Authentification par clé API (X-API-Key, X-Client-Type)
        │
        ▼
      FastAPI
        │
   ┌────┴─────────────────────────┐
   │                               │
Route /analyser              Route /chat
(analyse ponctuelle,          (conversation avec mémoire,
 pas de conversation)          détection d'intention)
   │                               │
   │                    ┌──────────┴──────────┐
   │                    │                      │
   │              Message normal      "Analyse ce dossier"
   │                    │                      │
   │                    ▼                      │
   │           Emma.chat_contextualise()       │
   │           (enveloppe JSON légère)         │
   │                    │                      │
   └────────────────────┼──────────────────────┘
                         ▼
                  Emma.analyser()
                         │
                         ▼
                 Prompt système Emma IA
              (hiérarchie des sources, garde-fous,
               distinction hypothèse/donnée/manquant)
                         │
                         ▼
                     DeepSeek
                         │
                         ▼
              Validation de la réponse
        (statuts, positions, niveaux de confiance
         contraints à des valeurs autorisées)
                         │
                         ▼
                 Réponse au client
```

---

## Principes de conception

Emma IA repose sur une séparation stricte entre trois rôles :

1. **Le moteur de règles métier** (externe à Emma IA) calcule les métriques officielles (ratio d'endettement, score de risque, etc.). Emma ne les recalcule jamais et ne les modifie jamais.
2. **Emma IA** analyse, structure, explique et signale — elle ne décide jamais d'une obligation documentaire, d'un seuil, ou d'une décision de crédit.
3. **L'analyste humain** valide, tranche, et reste responsable de la décision finale.

Toute donnée est classée dans l'une de ces catégories, jamais ambiguë :
- **Information vérifiée** — présente dans les documents ou données structurées transmises
- **Métrique officielle** — transmise explicitement par le moteur de règles, jamais déduite
- **Information contextuelle de l'analyste** — sans impact chiffré direct
- **Hypothèse non vérifiée** — donnée chiffrée non confirmée, qui impacterait un calcul si elle était vraie
- **Information manquante** — réellement absente, avec un statut d'obligation déterminé uniquement par la liste des exigences documentaires transmise par le système (jamais deviné par Emma)

---

## Contrat d'entrée

```json
{
  "donnees_dossier": {
    "demandeur": {},
    "demande": {
      "montant_demande": 0,
      "duree_demandee_mois": 0,
      "type_credit": ""
    },
    "revenus": {},
    "dettes": [],
    "historique_credit": {}
  },
  "metriques_officielles_calculees": {
    "ratio_endettement": "",
    "capacite_remboursement": "",
    "score_risque": 0,
    "montant_maximal_admissible": 0
  },
  "champs_obligatoires_pour_ce_produit": []
}
```
Exemple
```json
{
  "ticket_id": "TEST-HYP-001",
  "donnees_dossier": {
    "demandeur": {
      "id": "CLIENT-001"
    },
    "demande": {
      "montant_demande": 25000,
      "duree_demandee_mois": 60,
      "type_credit": "pret_personnel"
    },
    "revenus": {
      "revenu_mensuel": 4000,
      "periodicite": "mensuelle",
      "devise": "CAD",
      "type_revenu": "emploi",
      "source": "talon_paie",
      "statut_verification": "verifie"
    },
    "dettes": [
      {
        "type": "carte_credit",
        "solde": 3500,
        "mensualite": 150,
        "devise": "CAD",
        "source": "bureau_credit",
        "statut_verification": "verifie"
      },
      {
        "type": "pret_auto",
        "solde": 12000,
        "mensualite": 320,
        "devise": "CAD",
        "source": "bureau_credit",
        "statut_verification": "verifie"
      }
    ],
    "historique_credit": {
      "nombre_dossiers_anterieurs": 2,
      "taux_remboursement": 0.98,
      "nombre_retards": 1,
      "retards": [
        {
          "type": "retard_paiement",
          "nombre": 1
        }
      ],
      "statut_general": "historique_globalement_favorable"
    }
  },
  "metriques_officielles_calculees": {
    "ratio_endettement": 0.34,
    "capacite_remboursement": 820,
    "score_risque": 712
  },
  "champs_obligatoires_pour_ce_produit": [
    "preuve_revenu"
  ]
}
```
`champs_obligatoires_pour_ce_produit` est l'unique source autorisée pour qu'un champ manquant soit marqué `"obligatoire": true` dans la réponse. Emma IA ne déduit jamais elle-même qu'un document est obligatoire.

---

## Sécurité

- **Authentification par clé API** distincte pour le SaaS et la démo publique, deux niveaux de privilège séparés, aucune donnée réelle accessible depuis la démo.
- **Aucune donnée personnelle identifiable** ne doit transiter par Emma IA  le dossier est anonymisé en amont (identifiants uniquement).
- **Isolation stricte des dossiers**  chaque conversation reste ancrée sur un seul `ticket_id` pour toute sa durée ; aucun mélange entre dossiers n'est permis, y compris au niveau du prompt système.
- **Séparation confidentielle démo/SaaS** toute conversation de démo porte un `ticket_id` préfixé `DEMO-` et est purgée automatiquement après une durée d'inactivité configurable.

