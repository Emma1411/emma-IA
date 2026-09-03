Emma IA — Service d’Analyse de Crédit

Service backend d’analyse de crédit utilisant l’intelligence artificielle pour extraire, structurer et analyser des dossiers financiers, puis générer des synthèses et des recommandations.

Fonctionnalités
Analyse automatisée de dossiers de crédit
Extraction et structuration des données financières
Calcul et analyse des métriques
Détection de patterns et d’anomalies
Génération de synthèses et recommandations
Mode conversationnel avec Emma IA
API REST documentée avec Swagger / OpenAPI
Traçabilité des analyses
Stack technique
Python 3.11
FastAPI
DeepSeek
OpenAI SDK
Pydantic
Uvicorn / Gunicorn
Docker / Docker Compose
OpenAPI / Swagger
Architecture
Client
  │
  ▼
FastAPI
  │
  ▼
Business Logic
  │
  ├── Extraction & structuration
  ├── Métriques financières
  └── Détection d’anomalies
  │
  ▼
Emma IA
  │
  ├── Prompt système
  ├── Traitement des réponses
  └── Validation JSON
  │
  ▼
DeepSeek