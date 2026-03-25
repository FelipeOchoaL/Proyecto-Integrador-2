from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_patent_service
from app.models.patent import PaginatedResponse, Patent
from app.services.patent_service import PatentService

router = APIRouter(prefix="/patentes", tags=["patentes"])


@router.get("/", response_model=PaginatedResponse)
def list_patents(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    q: str | None = Query(None, min_length=1),
    service: PatentService = Depends(get_patent_service),
):
    if q:
        data, total = service.search(q, page, page_size)
    else:
        data, total = service.get_all(page, page_size)

    return PaginatedResponse(data=data, count=total, page=page, page_size=page_size)


@router.get("/{patent_id}", response_model=Patent)
def get_patent(
    patent_id: int,
    service: PatentService = Depends(get_patent_service),
):
    patent = service.get_by_id(patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patente no encontrada")
    return patent
