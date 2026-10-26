# Emma IA — Service d'Analyse de Crédit

Service backend d'analyse de crédit utilisant l'intelligence artificielle pour extraire, structurer et analyser des dossiers financiers, puis générer des synthèses et des recommandations.

Emma IA est un outil d'**assistance à la décision**, jamais un système de décision autonome — chaque appréciation qu'elle produit reste soumise à validation humaine.

Le backend est déployé sur **Google Cloud Run**, avec un pipeline de déploiement automatisé à partir de GitHub.

## Démonstration en ligne

| Ressource | Lien |
|---|---|
| API Emma IA | https://emma-ia-419943434355.northamerica-northeast1.run.app |
| Documentation interactive Swagger | https://emma-ia-419943434355.northamerica-northeast1.run.app/api/v1/docs |
| Health check | https://emma-ia-419943434355.northamerica-northeast1.run.app/api/v1/health |

**Hébergement :** Google Cloud Run  
**Région :** Montréal, Canada (`northamerica-northeast1`)  

---

## Fonctionnalités

- Analyse automatisée de dossiers de crédit à partir de données structurées.
- Extraction et structuration des données financières : revenus, dettes, historique de crédit et paramètres de la demande.
- Interprétation des métriques officielles calculées en amont par le moteur de règles (ratio d'endettement, capacité de remboursement, score de risque, montant maximal admissible) — jamais recalculées par Emma elle-même.
- Détection de patterns factuels : historique de crédit, tendances de revenu et incohérences documentaires.
- Génération de synthèses et d'appréciations analytiques traçables.
- Mode conversationnel avec mémoire : une conversation reste toujours ancrée sur un seul dossier.
- Gestion des hypothèses non vérifiées ajoutées par l'analyste en cours de conversation, reportées automatiquement dans toute analyse complète ultérieure.
- Deux surfaces d'accès distinctes : API SaaS authentifiée, liée aux dossiers clients, et API de démonstration publique, isolée et utilisant les dossiers fournis par le visiteur.
- Traçabilité des affirmations : chaque affirmation d'Emma est reliée à une donnée fournie, une métrique officielle ou une information explicitement identifiée comme non vérifiée.

---

## Stack technique

### Backend et IA

- Python 3.11
- FastAPI
- DeepSeek — moteur d'inférence LLM, via le SDK OpenAI
- Pydantic — validation des schémas d'entrée et de sortie
- Uvicorn / Gunicorn
- slowapi — limitation du débit des requêtes
- OpenAPI / Swagger

### Conteneurisation et cloud

- Docker / Docker Compose
- Google Cloud Run — hébergement du backend
- Google Cloud Build — construction et déploiement automatisés
- Google Artifact Registry — stockage des images Docker
- GitHub — gestion du code source et déclenchement du pipeline de déploiement

### Persistance

- PostgreSQL — métadonnées de conversation, selon la configuration
- Elasticsearch — historique des messages, selon la configuration


---

## Architecture

### Architecture applicative

```text
Client (SaaS ou Démo)
        |
        v
Authentification par clé API
(X-API-Key, X-Client-Type)
        |
        v
      FastAPI
        |
   +----+--------------------------+
   |                               |
   v                               v
Route /analyser                Route /chat
Analyse ponctuelle             Conversation avec mémoire
   |                               |
   |                     +---------+---------+
   |                     |                   |
   |                Message normal      Analyse du dossier
   |                     |                   |
   |                     v                   |
   |             Emma.chat_contextualise()   |
   |                     |                   |
   +---------------------+-------------------+
                         |
                         v
                   Emma.analyser()
                         |
                         v
                 Prompt système Emma IA
             (hiérarchie des sources, garde-fous,
              distinction hypothèse/donnée/manquant)
                         |
                         v
                      DeepSeek
                         |
                         v
                Validation de la réponse
                         |
                         v
                  Réponse JSON au client
```

### Architecture de déploiement cloud

```text
Développeur
    |
    v
GitHub — branche main
    |
    v
Google Cloud Build
    |
    v
Construction de l'image Docker
    |
    v
Google Artifact Registry
    |
    v
Google Cloud Run
    |
    v
API FastAPI — région Montréal
    |
    v
DeepSeek
```

Le pipeline est configuré pour construire et déployer le service à partir de la branche `main`. Après un déploiement, la nouvelle révision doit être vérifiée avant de considérer la mise à jour comme validée.

---

## Principes de conception

Emma IA repose sur une séparation stricte entre trois rôles :

1. **Le moteur de règles métier**, externe à Emma IA, calcule les métriques officielles (ratio d'endettement, score de risque, etc.). Emma ne les recalcule jamais et ne les modifie jamais.
2. **Emma IA** analyse, structure, explique et signale — elle ne décide jamais d'une obligation documentaire, d'un seuil ou d'une décision de crédit.
3. **L'analyste humain** valide, tranche et reste responsable de la décision finale.

Toute donnée est classée dans l'une de ces catégories, sans ambiguïté :

- **Information vérifiée** — présente dans les documents ou données structurées transmises.
- **Métrique officielle** — transmise explicitement par le moteur de règles, jamais déduite.
- **Information contextuelle de l'analyste** — sans impact chiffré direct.
- **Hypothèse non vérifiée** — donnée chiffrée non confirmée qui aurait un impact sur un calcul si elle était vraie.
- **Information manquante** — réellement absente, avec un statut d'obligation déterminé uniquement par la liste des exigences documentaires transmise par le système.

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

### Exemple de dossier

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

`champs_obligatoires_pour_ce_produit` est l'unique source autorisée pour qu'un champ manquant soit marqué `"obligatoire": true` dans la réponse.

Emma IA ne déduit jamais elle-même qu'un document est obligatoire.

---

## Routes API

| Méthode | Route | Description |
|---|---|---|
| GET | `/api/v1` | Informations sur le service |
| GET | `/api/v1/health` | Vérification de santé |
| POST | `/api/v1/analyser` | Analyse d'un dossier |
| POST | `/api/v1/conversations` | Démarrage d'une conversation |
| POST | `/api/v1/chat` | Conversation avec Emma |
| POST | `/api/v1/conversations/{conversation_id}/hypotheses` | Ajout d'une hypothèse SaaS |
| POST | `/api/v1/demo/chat` | Chat de démonstration |
| POST | `/api/v1/demo/analyser` | Analyse de démonstration |
| GET | `/api/v1/stats` | Statistiques du service |

La documentation Swagger permet de consulter les schémas, paramètres, en-têtes d'authentification et réponses détaillées :

https://emma-ia-419943434355.northamerica-northeast1.run.app/api/v1/docs

---

## Sécurité

- **Authentification par clé API** distincte pour le SaaS et la démo publique, avec deux niveaux de privilège séparés et aucune donnée réelle accessible depuis la démo.
- **Protection des données personnelles :** aucune donnée personnelle directement identifiable ne doit transiter par Emma IA ; le dossier est anonymisé en amont.
- **Isolation stricte des dossiers :** chaque conversation reste ancrée sur un seul `ticket_id` pendant toute sa durée ; aucun mélange entre dossiers n'est permis, y compris au niveau du prompt système.
- **Séparation confidentielle démo/SaaS :** toute conversation de démo porte un `ticket_id` préfixé par `DEMO-` et est purgée automatiquement après une durée d'inactivité configurable.
- **Gestion des secrets :** les clés API sont conservées dans des variables d'environnement ou un gestionnaire de secrets et ne sont jamais versionnées dans Git.
- **Validation humaine :** les réponses constituent une aide à l'analyse et ne remplacent pas la décision finale d'un analyste.

---

## Déploiement sur Google Cloud Run

Le backend est conteneurisé avec Docker et exécuté sur Google Cloud Run.

### Configuration actuelle

| Paramètre | Valeur |
|---|---|
| Service Cloud Run | `emma-ia` |
| Région | `northamerica-northeast1` |
| Port du conteneur | `8001` |
| CPU | 1 vCPU |
| Mémoire | 512 Mio |
| Instances minimales | 0 |
| Instances maximales | 2 |
| Facturation | À la requête |

la facturation dépend de l'utilisation, des quotas gratuits applicables et des autres services activés sur le compte Google Cloud.

### Déploiement automatisé

Le déclencheur Cloud Build est configuré pour déployer le service depuis la branche `main`.

Le flux de déploiement est le suivant :

1. Pousser les modifications sur GitHub.
2. Laisser Cloud Build construire l'image Docker.
3. Publier l'image dans Artifact Registry.
4. Déployer la nouvelle révision sur Cloud Run.
5. Vérifier la santé du service et tester les routes dans Swagger.


##
