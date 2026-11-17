from fastapi import APIRouter

from app.api.v1 import account, applications, core, discovery, jobs, outreach, people, resumes

api_router = APIRouter()
for module in (core, jobs, resumes, people, discovery, outreach, applications, account):
    api_router.include_router(module.router)
