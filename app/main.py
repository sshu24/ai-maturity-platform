from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import get_settings
from app.api.routes import auth, assessment, organisations, admin
from app.components.question_engine import load_question_bank
from fastapi.encoders import jsonable_encoder

settings = get_settings()

app = FastAPI(
    title="Project A — AI Maturity Platform",
    version="0.1.0",
    docs_url="/docs" if settings.ENV == "development" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(assessment.router)
app.include_router(organisations.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok", "env": settings.ENV}

@app.get("/questions")
def get_questions():
    bank = load_question_bank()
    return jsonable_encoder(bank)