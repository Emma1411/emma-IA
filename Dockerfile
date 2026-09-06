# Étape 1 : Build - Installation des dépendances
FROM python:3.11-slim AS builder

WORKDIR /app

# Dépendances système nécessaires à certaines librairies Python
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Étape 2 : Runtime
FROM python:3.11-slim

WORKDIR /app

# curl utilisé pour le healthcheck
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Utilisateur non-root
RUN addgroup --system --gid 1001 emma && \
    adduser --system --uid 1001 --gid 1001 emma

# Copier les dépendances Python
COPY --from=builder /usr/local/lib/python3.11/site-packages \
    /usr/local/lib/python3.11/site-packages

COPY --from=builder /usr/local/bin \
    /usr/local/bin

# Copier l'application
COPY app/ ./app/
COPY main.py .

# Permissions
RUN chown -R emma:emma /app

# Utilisateur non-root
USER emma

# Port de l'application
EXPOSE 8001

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/api/v1/health || exit 1

# Démarrage de l'application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
