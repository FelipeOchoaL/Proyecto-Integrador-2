from pydantic import BaseModel


class Patent(BaseModel):
    id: int | None = None
    pn: str | None = None
    pc: str | None = None
    cpc: str | None = None
    ic: str | None = None
    ws: str | None = None
    ls: str | None = None
    ti: str | None = None
    ab: str | None = None
    descripcion: str | None = None
    claimen: str | None = None
    espacenet: str | None = None


class PatentSummary(BaseModel):
    """Versión ligera sin campos de texto largo."""

    id: int | None = None
    pn: str | None = None
    pc: str | None = None
    cpc: str | None = None
    ic: str | None = None
    ws: str | None = None
    ls: str | None = None
    ti: str | None = None
    ab: str | None = None
    espacenet: str | None = None


class PaginatedResponse(BaseModel):
    data: list[PatentSummary]
    count: int
    page: int
    page_size: int
