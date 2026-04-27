from fastapi import APIRouter

from api.v1 import auth, meeting_recordings, meetings, members, sessions, stats, transcripts, users
from routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router)
api_router.include_router(members.router)
api_router.include_router(meetings.router)
api_router.include_router(meeting_recordings.router)
api_router.include_router(transcripts.router)
api_router.include_router(sessions.router)
api_router.include_router(stats.router)
