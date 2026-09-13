import pandas as pd

from app.cleaning import (
    clean_status,
    email_domain,
    name_block_key,
    normalize_phone,
    parse_date,
    resolve_names,
)
from app.models import Lead


def load_csv_into_db(csv_path: str, db):
    if db.query(Lead).first() is not None:
        return 0  # already loaded

    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    inserted = 0

    for _, row in df.iterrows():
        first, last, full = resolve_names(
            row.get("First Name"), row.get("Last Name"), row.get("Full Name")
        )
        phone_norm = normalize_phone(row.get("Phone Number"))
        domain = email_domain(row.get("Email"))
        name_key = name_block_key(full, row.get("Company Name"))

        lead = Lead(
            record_id=row.get("Record ID") or None,
            first_name=first,
            last_name=last,
            full_name=full,
            job_title=row.get("Job Title") or None,
            company_name=row.get("Company Name") or None,
            email=row.get("Email") or None,
            phone_number=row.get("Phone Number") or None,
            phone_normalized=phone_norm,
            country=row.get("Country/Region") or None,
            city=row.get("City") or None,
            status=clean_status(row.get("Lead Status")),
            lifecycle_stage=row.get("Lifecycle Stage") or None,
            original_source=row.get("Original Source") or None,
            original_source_drilldown=row.get("Original Source Drill-Down 1") or None,
            contact_owner=(row.get("Contact Owner") or "").strip() or None,
            create_date=parse_date(row.get("Create Date")),
            last_modified_date=parse_date(row.get("Last Modified Date")),
            notes=row.get("Notes") or None,
            block_email_domain=domain,
            block_name_key=name_key,
        )
        db.add(lead)
        inserted += 1

    db.commit()
    return inserted
