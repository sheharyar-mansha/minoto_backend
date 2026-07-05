"""Run from this folder: uvicorn main:app --reload"""

import hf_hub_compat
import torch_load_compat

hf_hub_compat.apply_hf_hub_use_auth_token_compat()
torch_load_compat.apply_torch_load_compat()

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
