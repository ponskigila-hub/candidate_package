import csv
import io
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.cleaning import email_domain, name_block_key, normalize_phone, resolve_names
from app.database import Base, SessionLocal, engine, get_db
from app.data_loader import load_csv_into_db
from app.dedup import find_dedup_candidates, group_candidates
from app.models import Lead
from app.schemas import IngestPayload, LeadUpdate
from app.source_extraction import extract_source

Base.metadata.create_all(bind=engine)

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "leads_seed.csv")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        load_csv_into_db(CSV_PATH, db)
    finally:
        db.close()
    yield


app = FastAPI(title="LeadFlow", description="Mini lead management API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local take-home scope; would restrict in a real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/leads")
def list_leads(
    status: str | None = None,
    owner: str | None = None,
    country: str | None = None,
    q: str | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(Lead)
    if status:
        query = query.filter(Lead.status.ilike(status))
    if owner:
        query = query.filter(Lead.contact_owner.ilike(owner))
    if country:
        query = query.filter(Lead.country.ilike(country))
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Lead.full_name.ilike(like),
                Lead.company_name.ilike(like),
                Lead.email.ilike(like),
            )
        )
    total = query.count()
    leads = query.order_by(Lead.id).offset(offset).limit(limit).all()
    return {"total": total, "limit": limit, "offset": offset, "leads": [l.to_dict() for l in leads]}


@app.get("/leads/export")
def export_leads(
    status: str | None = None,
    owner: str | None = None,
    country: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Lead)
    if status:
        query = query.filter(Lead.status.ilike(status))
    if owner:
        query = query.filter(Lead.contact_owner.ilike(owner))
    if country:
        query = query.filter(Lead.country.ilike(country))
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(Lead.full_name.ilike(like), Lead.company_name.ilike(like), Lead.email.ilike(like))
        )
    leads = query.order_by(Lead.id).all()

    buf = io.StringIO()
    fieldnames = list(leads[0].to_dict().keys()) if leads else ["id"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for lead in leads:
        writer.writerow(lead.to_dict())
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_export.csv"},
    )


@app.get("/leads/{lead_id}")
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead.to_dict()


@app.patch("/leads/{lead_id}")
def update_lead(lead_id: int, payload: LeadUpdate, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if payload.status is not None:
        lead.status = payload.status.strip().title()
    if payload.contact_owner is not None:
        lead.contact_owner = payload.contact_owner
    if payload.notes is not None:
        lead.notes = payload.notes
    db.commit()
    db.refresh(lead)
    return lead.to_dict()


def _find_existing_match(db: Session, email: str | None, phone_norm: str | None) -> Lead | None:
    """Exact-match dedup for ingest: same email, or same last-8-digits phone.
    (The fuzzy/embedding dedup pipeline is for surfacing *likely* duplicates
    for human review - ingest-time matching stays conservative/exact so we
    never silently merge two different people.)"""
    if email:
        existing = db.query(Lead).filter(Lead.email.ilike(email)).first()
        if existing:
            return existing
    if phone_norm and len(phone_norm) >= 6:
        suffix = phone_norm[-8:]
        candidates = db.query(Lead).filter(Lead.phone_normalized.isnot(None)).all()
        for c in candidates:
            if c.phone_normalized and c.phone_normalized[-8:] == suffix:
                return c
    return None


@app.post("/leads/ingest")
def ingest_lead(payload: IngestPayload, db: Session = Depends(get_db)):
    first, last, full = resolve_names(None, None, payload.name)
    phone_norm = normalize_phone(payload.phone)
    domain = email_domain(payload.email)

    existing = _find_existing_match(db, payload.email, phone_norm)
    extraction = extract_source(payload.message, None)

    if existing:
        # Update rather than duplicate.
        if payload.message:
            existing.notes = (
                f"{existing.notes}\n---\n{payload.message}" if existing.notes else payload.message
            )
        existing.extracted_channel = extraction.channel
        existing.extracted_detail = extraction.detail
        if payload.company and not existing.company_name:
            existing.company_name = payload.company
        db.commit()
        db.refresh(existing)
        return {"action": "updated", "lead": existing.to_dict()}

    lead = Lead(
        first_name=first,
        last_name=last,
        full_name=full,
        company_name=payload.company,
        email=payload.email,
        phone_number=payload.phone,
        phone_normalized=phone_norm,
        country=payload.country,
        status="New",
        lifecycle_stage="Lead",
        contact_owner=None,
        notes=payload.message,
        block_email_domain=domain,
        block_name_key=name_block_key(full, payload.company),
        extracted_channel=extraction.channel,
        extracted_detail=extraction.detail,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return {"action": "created", "lead": lead.to_dict()}


@app.post("/leads/dedupe-candidates")
def dedupe_candidates(db: Session = Depends(get_db)):
    leads = db.query(Lead).all()
    candidates = find_dedup_candidates(leads)
    groups = group_candidates(candidates)

    # Attach lead summaries for readability
    lead_by_id = {l.id: l for l in leads}
    for group in groups:
        group["leads"] = [
            {
                "id": lid,
                "full_name": lead_by_id[lid].full_name,
                "email": lead_by_id[lid].email,
                "company_name": lead_by_id[lid].company_name,
                "phone_number": lead_by_id[lid].phone_number,
            }
            for lid in group["lead_ids"]
        ]
    return {"group_count": len(groups), "groups": groups}


@app.post("/leads/{lead_id}/extract-source")
def extract_lead_source(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    result = extract_source(lead.notes, lead.original_source)
    lead.extracted_channel = result.channel
    lead.extracted_detail = result.detail
    db.commit()
    return {"channel": result.channel, "detail": result.detail, "method": result.method}


@app.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    leads = db.query(Lead).all()
    by_status: dict[str, int] = {}
    by_channel: dict[str, int] = {}
    for lead in leads:
        s = lead.status or "Unknown"
        by_status[s] = by_status.get(s, 0) + 1
        c = lead.extracted_channel
        if not c:
            # lazily classify if not already done, for accurate dashboard counts
            c = extract_source(lead.notes, lead.original_source).channel
        by_channel[c] = by_channel.get(c, 0) + 1
    return {
        "total_leads": len(leads),
        "by_status": dict(sorted(by_status.items(), key=lambda x: -x[1])),
        "by_source_channel": dict(sorted(by_channel.items(), key=lambda x: -x[1])),
    }
