from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.dependencies import get_patent_service
from app.models.patent import (
    PaginatedResponse,
    Patent,
    SemanticSearchRequest,
    SemanticSearchResponse,
    SimilarPatentsResponse,
)
from app.services.patent_service import PatentService
from app.services.pdf_service import generar_pdf_resultados

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


@router.post("/search/semantic", response_model=SemanticSearchResponse)
def search_semantic(
    payload: SemanticSearchRequest,
    service: PatentService = Depends(get_patent_service),
):
    """Búsqueda híbrida BM25 + Sentence-BERT con fusión RRF.

    A diferencia de `GET /patentes/?q=`, este endpoint:
      * calcula el embedding de la query con Sentence-BERT,
      * llama al RPC `search_patentes_hybrid` en Supabase,
      * devuelve los resultados ordenados por `rrf_score`.
    """
    results = service.search_semantic(payload.query, payload.top_k)
    return SemanticSearchResponse(
        query=payload.query,
        data=results,
        count=len(results),
    )


@router.post("/export/pdf")
def export_pdf(
    payload: SemanticSearchRequest,
    service: PatentService = Depends(get_patent_service),
):
    """Genera un PDF con los resultados de la búsqueda semántica y un resumen por clusters."""
    resultados = service.search_semantic(payload.query, payload.top_k)

    if not resultados:
        raise HTTPException(status_code=404, detail="No se encontraron resultados para exportar")

    pdf_bytes = generar_pdf_resultados(payload.query, resultados)

    # Nombre del archivo: reemplazar espacios por guiones para que sea un nombre válido
    nombre_archivo = f"patentologos_{payload.query[:30].replace(' ', '_')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"},
    )


@router.get("/{patent_id}/similares", response_model=SimilarPatentsResponse)
def get_similares(
    patent_id: int,
    top_k: int = Query(10, ge=1, le=50),
    service: PatentService = Depends(get_patent_service),
):
    """Patentes más cercanas a la dada (KNN puro sobre embedding)."""
    results = service.get_similares(patent_id, top_k)
    return SimilarPatentsResponse(
        patent_id=patent_id,
        data=results,
        count=len(results),
    )


@router.get("/{patent_id}", response_model=Patent)
def get_patent(
    patent_id: int,
    service: PatentService = Depends(get_patent_service),
):
    patent = service.get_by_id(patent_id)
    if not patent:
        raise HTTPException(status_code=404, detail="Patente no encontrada")
    return patent

