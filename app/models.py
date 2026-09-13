from sqlalchemy import Column, Integer, String, Text, DateTime
from app.database import Base


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(String, unique=True, index=True, nullable=True)

    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    full_name = Column(String, nullable=True)  # cleaned, always populated
    job_title = Column(String, nullable=True)
    company_name = Column(String, nullable=True, index=True)
    email = Column(String, nullable=True, index=True)
    phone_number = Column(String, nullable=True)
    phone_normalized = Column(String, nullable=True, index=True)  # digits only
    country = Column(String, nullable=True, index=True)
    city = Column(String, nullable=True)

    status = Column(String, nullable=True, index=True)  # normalized casing
    lifecycle_stage = Column(String, nullable=True)

    original_source = Column(String, nullable=True)
    original_source_drilldown = Column(String, nullable=True)
    contact_owner = Column(String, nullable=True, index=True)

    create_date = Column(DateTime, nullable=True)
    last_modified_date = Column(DateTime, nullable=True)

    notes = Column(Text, nullable=True)

    # AI-derived source extraction (populated lazily / on ingest)
    extracted_channel = Column(String, nullable=True, index=True)
    extracted_detail = Column(String, nullable=True)

    # blocking keys, precomputed for fast dedup candidate generation
    block_email_domain = Column(String, nullable=True, index=True)
    block_name_key = Column(String, nullable=True, index=True)  # soundex-ish key

    def to_dict(self):
        return {
            "id": self.id,
            "record_id": self.record_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "job_title": self.job_title,
            "company_name": self.company_name,
            "email": self.email,
            "phone_number": self.phone_number,
            "country": self.country,
            "city": self.city,
            "status": self.status,
            "lifecycle_stage": self.lifecycle_stage,
            "original_source": self.original_source,
            "original_source_drilldown": self.original_source_drilldown,
            "contact_owner": self.contact_owner,
            "create_date": self.create_date.isoformat() if self.create_date else None,
            "last_modified_date": self.last_modified_date.isoformat()
            if self.last_modified_date
            else None,
            "notes": self.notes,
            "extracted_channel": self.extracted_channel,
            "extracted_detail": self.extracted_detail,
        }
