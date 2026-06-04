from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship, DeclarativeBase
import enum


class Base(DeclarativeBase):
    pass


class DocumentStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    hitl_pending = "hitl_pending"
    hitl_resolved = "hitl_resolved"


class DocumentType(str, enum.Enum):
    i129 = "i129"
    i140 = "i140"
    i485 = "i485"
    passport = "passport"
    visa = "visa"
    l1_petition = "l1_petition"
    ds160 = "ds160"
    eea_form = "eea_form"
    biometric = "biometric"
    other = "other"


class HITLPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    firm_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    documents = relationship("Document", back_populates="owner")


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_name = Column(String(500), nullable=False)
    file_path = Column(String(1000))
    file_size_bytes = Column(Integer)
    page_count = Column(Integer)
    document_type = Column(SAEnum(DocumentType), default=DocumentType.other)
    detected_type = Column(String(50))
    applicant_name = Column(String(255))
    applicant_dob = Column(String(50))
    applicant_nationality = Column(String(100))
    passport_number = Column(String(100))
    passport_expiry = Column(String(50))
    petition_number = Column(String(100))
    employer_name = Column(String(255))
    visa_classification = Column(String(50))
    priority_date = Column(String(50))
    validity_start = Column(String(50))
    validity_end = Column(String(50))
    consulate = Column(String(200))
    job_title = Column(String(255))
    wage = Column(String(100))
    ai_confidence = Column(Float)
    extraction_model = Column(String(100))
    used_fallback = Column(Boolean, default=False)
    raw_extracted_json = Column(Text)
    status = Column(SAEnum(DocumentStatus), default=DocumentStatus.queued)
    error_message = Column(Text)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))
    owner = relationship("User", back_populates="documents")
    fields = relationship("ExtractedField", back_populates="document", cascade="all, delete-orphan")
    hitl_items = relationship("HITLQueueItem", back_populates="document", cascade="all, delete-orphan")


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    field_name = Column(String(200), nullable=False)
    field_value = Column(Text)
    field_type = Column(String(50), default="string")
    confidence = Column(Float, nullable=False)
    is_verified = Column(Boolean, default=False)
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime(timezone=True))
    original_value = Column(Text)
    page_number = Column(Integer)
    document = relationship("Document", back_populates="fields")


class HITLQueueItem(Base):
    __tablename__ = "hitl_queue"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    reason = Column(String(500))
    priority = Column(SAEnum(HITLPriority), default=HITLPriority.medium)
    flagged_fields = Column(Text)
    overall_confidence = Column(Float)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime(timezone=True))
    notes = Column(Text)
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    document = relationship("Document", back_populates="hitl_items")
