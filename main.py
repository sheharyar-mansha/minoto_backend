"""Run from this folder: uvicorn main:app --reload"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from routes.health import router as health_router

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

# Lets browser-based frontends (e.g. Next.js on localhost) call the API. Mobile apps ignore CORS.
_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.API_V1_PREFIX)
