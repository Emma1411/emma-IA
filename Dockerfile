# Étape 1: Build - Installation des dépendances
FROM python:3.11-slim AS builder

WORKDIR /app

# Installer les dépendances système nécessaires
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Étape 2: Runtime - Image finale
FROM python:3.11-slim

WORKDIR /app

# Installer curl pour les healthchecks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Créer un utilisateur non-root pour la sécurité
RUN addgroup --system --gid 1001 emma && \
    adduser --system --uid 1001 --gid 1001 emma

# Copier les dépendances depuis le builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copier le code de l'application
COPY app/ ./app/

# Copier .env.example s'il existe, ou créer un fichier vide
# (Supprimer ou commenter la ligne suivante qui copie .env)
# COPY .env .env

# Créer un fichier .env vide si nécessaire
RUN touch .env

# Changer les permissions
RUN chown -R emma:emma /app

# Passer à l'utilisateur non-root
USER emma

# Exposer le port
EXPOSE 8001

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/api/v1/health || exit 1

# Lancer avec Gunicorn (production)
CMD ["gunicorn", "app.main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8001", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--log-level", "info"]