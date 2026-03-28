"""Run from this folder: uvicorn main:app --reload"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.v1.router import api_router
from config.settings import UPLOAD_DIR, settings

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# StaticFiles requires the directory to exist at import time (before startup handlers run).
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/media", StaticFiles(directory=str(UPLOAD_DIR)), name="media")

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
