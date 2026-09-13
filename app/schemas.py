from typing import Optional

from pydantic import BaseModel, ConfigDict


class LeadUpdate(BaseModel):
    status: Optional[str] = None
    contact_owner: Optional[str] = None
    notes: Optional[str] = None


class IngestPayload(BaseModel):
    """Mirrors data/website_form_submissions.json entry shape:
    {form_id, form_name, page_url, submitted_at, name, email, phone,
     company, country, message}.
    `name` is a single full-name field here (unlike the CSV's split
    columns) - handled via resolve_names() same as the CSV loader."""

    form_id: Optional[str] = None
    form_name: Optional[str] = None
    page_url: Optional[str] = None
    submitted_at: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    country: Optional[str] = None
    message: Optional[str] = None

    model_config = ConfigDict(extra="allow")  # tolerate extra/unexpected form fields
