from __future__ import annotations

from app.core.exceptions import NotFoundError, UnprocessableError
from app.db.pool import Database
from app.modules.audit import repository as audit
from app.modules.companies import repository as repo
from app.modules.companies.ats import detect_ats
from app.modules.companies.schemas import CompanyCreate, CompanyOut, CompanyUpdate
from app.shared.pagination import Page, decode_cursor, paginate
from app.shared.text import company_key, escape_like


def create(db: Database, body: CompanyCreate) -> CompanyOut:
    key = company_key(body.name)
    if not key:
        raise UnprocessableError("Company name must contain letters or digits.")
    careers_url = str(body.careers_url) if body.careers_url else None
    ats_kind, ats_token = body.ats_kind, body.ats_token
    if ats_kind is None and careers_url:
        board = detect_ats(careers_url)
        if board is not None:
            ats_kind, ats_token = board.kind, board.token

    values = {
        "name": body.name,
        "normalized_key": key,
        "website_url": str(body.website_url) if body.website_url else None,
        "careers_url": careers_url,
        "ats_kind": ats_kind,
        "ats_token": ats_token.lower() if ats_token else None,
        "enabled": body.enabled,
        "notes": body.notes,
    }
    with db.transaction() as cur:
        row = repo.insert(cur, values)
        audit.record(
            cur,
            actor="user",
            action="company.created",
            entity_type="company",
            entity_id=row["id"],
            details={"ats_kind": ats_kind},
        )
    return CompanyOut.model_validate(row)


def get(db: Database, company_id: int) -> CompanyOut:
    with db.transaction() as cur:
        row = repo.get(cur, company_id)
    if row is None:
        raise NotFoundError(f"Company {company_id} not found.")
    return CompanyOut.model_validate(row)


def list_page(
    db: Database,
    *,
    enabled: bool | None,
    ats_kind: str | None,
    q: str | None,
    limit: int,
    cursor: str | None,
) -> Page[CompanyOut]:
    after = str(decode_cursor(cursor, 1)[0]) if cursor else None
    q_like = f"%{escape_like(q)}%" if q else None
    with db.transaction() as cur:
        rows = repo.list_companies(
            cur, enabled=enabled, ats_kind=ats_kind, q_like=q_like, after=after, limit=limit
        )
    page, next_cursor = paginate(rows, limit, key=lambda r: (r["normalized_key"],))
    return Page(items=[CompanyOut.model_validate(r) for r in page], next_cursor=next_cursor)


def update(db: Database, company_id: int, body: CompanyUpdate) -> CompanyOut:
    changes = body.model_dump(exclude_unset=True, mode="json")
    if "name" in changes:
        if not changes["name"]:
            raise UnprocessableError("name cannot be null.")
        changes["normalized_key"] = company_key(changes["name"])
    if "enabled" in changes and changes["enabled"] is None:
        raise UnprocessableError("enabled cannot be null.")
    with db.transaction() as cur:
        row = repo.update(cur, company_id, changes) if changes else repo.get(cur, company_id)
        if row is None:
            raise NotFoundError(f"Company {company_id} not found.")
        if changes:
            audit.record(
                cur,
                actor="user",
                action="company.updated",
                entity_type="company",
                entity_id=company_id,
                details={"fields": sorted(changes)},
            )
    return CompanyOut.model_validate(row)


def delete(db: Database, company_id: int) -> None:
    with db.transaction() as cur:
        if not repo.delete(cur, company_id):
            raise NotFoundError(f"Company {company_id} not found.")
        audit.record(
            cur, actor="user", action="company.deleted", entity_type="company", entity_id=company_id
        )
