from __future__ import annotations
import asyncio, csv, io, json, os, uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from database.connection import get_db
from database.models import Document, DocumentStatus, DocumentType, ExtractedField, HITLQueueItem
from auth.jwt import get_current_user
from database.models import User
from extractor.pipeline import process_document
from config import get_settings

settings = get_settings()
router = APIRouter(prefix="/documents", tags=["documents"])
UPLOAD_DIR = "/tmp/docverify"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class DocSummary(BaseModel):
    id: int; file_name: str; document_type: Optional[str]; detected_type: Optional[str]
    status: str; ai_confidence: Optional[float]; applicant_name: Optional[str]
    visa_classification: Optional[str]; uploaded_at: datetime; processed_at: Optional[datetime]
    used_fallback: bool = False
    model_config = ConfigDict(from_attributes=True)


class DocDetail(DocSummary):
    applicant_dob: Optional[str]; applicant_nationality: Optional[str]
    passport_number: Optional[str]; passport_expiry: Optional[str]
    petition_number: Optional[str]; employer_name: Optional[str]
    priority_date: Optional[str]; validity_start: Optional[str]; validity_end: Optional[str]
    consulate: Optional[str]; job_title: Optional[str]; wage: Optional[str]
    extraction_model: Optional[str]; error_message: Optional[str]; page_count: Optional[int]


class FieldOut(BaseModel):
    id: int; field_name: str; field_value: Optional[str]; confidence: float
    is_verified: bool; page_number: Optional[int]
    model_config = ConfigDict(from_attributes=True)


class VerifyPayload(BaseModel):
    corrected_value: Optional[str] = None


class Stats(BaseModel):
    total: int; completed: int; hitl_pending: int; failed: int
    avg_confidence: Optional[float]; auto_verified_fields: int; flagged_fields: int


@router.post("/upload", status_code=202)
async def upload(bg: BackgroundTasks, file: UploadFile = File(...),
                 document_type: DocumentType = DocumentType.other,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF only")
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"Exceeds {settings.max_upload_size_mb}MB")
    path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{file.filename}")
    with open(path, "wb") as f: f.write(data)
    doc = Document(owner_id=user.id, file_name=file.filename, file_path=path,
                   file_size_bytes=len(data), document_type=document_type)
    db.add(doc); db.commit(); db.refresh(doc)
    bg.add_task(process_document, doc.id)
    return {"job_id": doc.id, "status": "queued"}


@router.post("/batch/upload", status_code=202)
async def batch_upload(bg: BackgroundTasks, files: list[UploadFile] = File(...),
                       document_type: DocumentType = DocumentType.other,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if len(files) > 20: raise HTTPException(400, "Max 20 files")
    ids = []
    for file in files:
        if not file.filename.lower().endswith(".pdf"): continue
        data = await file.read()
        path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{file.filename}")
        with open(path, "wb") as f: f.write(data)
        doc = Document(owner_id=user.id, file_name=file.filename, file_path=path,
                       file_size_bytes=len(data), document_type=document_type)
        db.add(doc); db.commit(); db.refresh(doc)
        ids.append(doc.id)
        bg.add_task(process_document, doc.id)
    return {"job_ids": ids, "count": len(ids)}


@router.get("/", response_model=list[DocSummary])
def list_docs(status: Optional[str] = None, document_type: Optional[str] = None,
              limit: int = Query(50, le=200), offset: int = 0,
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Document).filter(Document.owner_id == user.id)
    if status: q = q.filter(Document.status == status)
    if document_type: q = q.filter(Document.document_type == document_type)
    return q.order_by(Document.uploaded_at.desc()).offset(offset).limit(limit).all()


@router.get("/stats/summary", response_model=Stats)
def stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    docs = db.query(Document).filter(Document.owner_id == user.id).all()
    confs = [d.ai_confidence for d in docs if d.ai_confidence is not None]
    fields = db.query(ExtractedField).join(Document).filter(Document.owner_id == user.id).all()
    return Stats(
        total=len(docs),
        completed=sum(1 for d in docs if d.status == DocumentStatus.completed),
        hitl_pending=sum(1 for d in docs if d.status == DocumentStatus.hitl_pending),
        failed=sum(1 for d in docs if d.status == DocumentStatus.failed),
        avg_confidence=round(sum(confs) / len(confs), 3) if confs else None,
        auto_verified_fields=sum(1 for f in fields if f.confidence >= 0.90),
        flagged_fields=sum(1 for f in fields if f.confidence < 0.75),
    )


@router.get("/search")
def search(q: str = Query(..., min_length=2), db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    t = f"%{q}%"
    return db.query(Document).filter(Document.owner_id == user.id).filter(
        Document.applicant_name.ilike(t) | Document.employer_name.ilike(t) |
        Document.passport_number.ilike(t) | Document.petition_number.ilike(t) |
        Document.file_name.ilike(t)
    ).limit(50).all()


@router.get("/export")
def export(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    docs = db.query(Document).filter(Document.owner_id == user.id).all()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id","file_name","document_type","status","applicant_name",
                "visa_classification","ai_confidence","employer_name","passport_number",
                "priority_date","uploaded_at"])
    for d in docs:
        w.writerow([d.id,d.file_name,d.document_type,d.status,d.applicant_name,
                    d.visa_classification,d.ai_confidence,d.employer_name,
                    d.passport_number,d.priority_date,d.uploaded_at])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=documents.csv"})


@router.get("/hitl/queue")
def hitl_queue(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (db.query(HITLQueueItem).join(Document)
            .filter(Document.owner_id == user.id, HITLQueueItem.is_resolved == False)
            .order_by(HITLQueueItem.created_at.desc()).all())


@router.post("/hitl/{hitl_id}/resolve")
def resolve_hitl(hitl_id: int, notes: Optional[str] = None,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.query(HITLQueueItem).filter(HITLQueueItem.id == hitl_id).first()
    if not item: raise HTTPException(404, "Not found")
    item.is_resolved = True
    item.resolved_by = user.id
    item.resolved_at = datetime.now(timezone.utc)
    item.notes = notes
    item.document.status = DocumentStatus.hitl_resolved
    db.commit()
    return {"message": "Resolved"}


@router.get("/{doc_id}/status")
def get_status(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = _or_404(doc_id, db, user)
    return {"id": d.id, "status": d.status, "ai_confidence": d.ai_confidence}


@router.get("/{doc_id}", response_model=DocDetail)
def get_doc(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _or_404(doc_id, db, user)


@router.get("/{doc_id}/fields", response_model=list[FieldOut])
def get_fields(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _or_404(doc_id, db, user)
    return db.query(ExtractedField).filter(ExtractedField.document_id == doc_id).all()


@router.patch("/{doc_id}/fields/{fid}/verify")
def verify(doc_id: int, fid: int, payload: VerifyPayload,
           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _or_404(doc_id, db, user)
    ef = db.query(ExtractedField).filter(ExtractedField.id == fid,
                                          ExtractedField.document_id == doc_id).first()
    if not ef: raise HTTPException(404, "Field not found")
    if payload.corrected_value is not None:
        ef.original_value = ef.field_value
        ef.field_value = payload.corrected_value
    ef.is_verified = True
    ef.verified_by = user.id
    ef.verified_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Verified"}


@router.post("/{doc_id}/reprocess", status_code=202)
async def reprocess(doc_id: int, bg: BackgroundTasks,
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = _or_404(doc_id, db, user)
    doc.status = DocumentStatus.queued; doc.error_message = None
    db.commit()
    bg.add_task(process_document, doc_id)
    return {"message": "Reprocessing", "job_id": doc_id}


@router.delete("/{doc_id}", status_code=204)
def delete(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = _or_404(doc_id, db, user)
    if doc.file_path and os.path.exists(doc.file_path): os.remove(doc.file_path)
    db.delete(doc); db.commit()


def _or_404(doc_id: int, db: Session, user: User) -> Document:
    d = db.query(Document).filter(Document.id == doc_id, Document.owner_id == user.id).first()
    if not d: raise HTTPException(404, "Not found")
    return d
