# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.models import DossierAnalyseRequest, ChatInput
from app.emma_ia import EmmaIA
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Emma IA - SecureFinance-RAG",
    version="2.1.2",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    emma = EmmaIA()
    logger.info("Emma IA initialisée")
except Exception as e:
    logger.error(f"Erreur : {e}")
    emma = None


@app.get("/api/v1")
async def root():
    return {"service": "Emma IA", "version": "2.1.2", "status": "ok" if emma else "error"}


@app.get("/api/v1/health")
async def health():
    return {"status": "healthy" if emma else "unavailable"}


@app.post("/api/v1/analyser")
async def analyser_dossier(dossier: DossierAnalyseRequest):
    if not emma:
        raise HTTPException(status_code=503, detail="Emma indisponible")
    try:
        return emma.analyser(dossier.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/chat")
async def chat_avec_emma(chat: ChatInput):
    if not emma:
        raise HTTPException(status_code=503, detail="Emma indisponible")
    try:
        return {"reponse": emma.chat(chat.message)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/stats")
async def get_stats():
    if not emma:
        raise HTTPException(status_code=503, detail="Emma indisponible")
    return emma.get_stats()