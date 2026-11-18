from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.api.deps import DbDep
from app.modules.companies import service
from app.modules.companies.ats import AtsKind, detect_ats
from app.modules.companies.schemas import (
    AtsDetectRequest,
    AtsDetectResponse,
    CompanyCreate,
    CompanyOut,
    CompanyUpdate,
)
from app.shared.pagination import CursorParam, LimitParam, Page
from app.shared.schemas import ERROR_RESPONSES

router = APIRouter(prefix="/companies", tags=["companies"], responses=ERROR_RESPONSES)

CompanyId = Annotated[int, Path(ge=1)]


@router.post(
    "/detect-ats", response_model=AtsDetectResponse, summary="Detect the ATS behind a careers URL"
)
def detect(body: AtsDetectRequest) -> AtsDetectResponse:
    board = detect_ats(str(body.url))
    if board is None:
        return AtsDetectResponse(detected=False)
    return AtsDetectResponse(detected=True, ats_kind=board.kind, ats_token=board.token)


@router.get("", response_model=Page[CompanyOut], summary="List companies (A-Z)")
def list_companies(
    db: DbDep,
    q: Annotated[
        str | None, Query(min_length=1, max_length=100, description="Name contains")
    ] = None,
    enabled: bool | None = None,
    ats_kind: AtsKind | None = None,
    limit: LimitParam = 50,
    cursor: CursorParam = None,
) -> Page[CompanyOut]:
    return service.list_page(
        db, enabled=enabled, ats_kind=ats_kind, q=q, limit=limit, cursor=cursor
    )


@router.post(
    "",
    response_model=CompanyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a company to watch",
)
def create_company(db: DbDep, body: CompanyCreate) -> CompanyOut:
    return service.create(db, body)


@router.get("/{company_id}", response_model=CompanyOut, summary="Get a company")
def get_company(db: DbDep, company_id: CompanyId) -> CompanyOut:
    return service.get(db, company_id)


@router.patch("/{company_id}", response_model=CompanyOut, summary="Update a company")
def update_company(db: DbDep, company_id: CompanyId, body: CompanyUpdate) -> CompanyOut:
    return service.update(db, company_id, body)


@router.delete(
    "/{company_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a company and its jobs"
)
def delete_company(db: DbDep, company_id: CompanyId) -> None:
    service.delete(db, company_id)
