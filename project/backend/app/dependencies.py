from app.database import supabase
from app.services.patent_service import PatentService

_patent_service = PatentService(supabase)


def get_patent_service() -> PatentService:
    return _patent_service
