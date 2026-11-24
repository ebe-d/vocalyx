from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.database import Base


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    notes = Column(Text, nullable=True)
    last_topic = Column(String, nullable=True)
    interest_level = Column(String, default="Unknown")  # High/Medium/Low/Unknown
    concerns = Column(Text, nullable=True)
    commitments = Column(Text, nullable=True)
    last_contacted_at = Column(DateTime, nullable=True)
    preferred_language = Column(String, default="en-US")  # e.g. en-US, hi-IN, kn-IN

    calls = relationship("Call", back_populates="contact")


class Script(Base):
    __tablename__ = "scripts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)


class Call(Base):
    __tablename__ = "calls"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False)
    transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    sentiment = Column(String, nullable=True)       # Positive/Neutral/Negative
    outcome = Column(String, nullable=True)         # Interested/Not Interested/Requested Callback/Time-Waster/Needs Follow-up
    lead_score = Column(Integer, nullable=True)     # 0-100
    lead_score_reasoning = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    contact = relationship("Contact", back_populates="calls")


class Voice(Base):
    __tablename__ = "voices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    engine = Column(String, default="f5tts")  # f5tts, luxtts, polly, kannada, hindi
    voice_type = Column(String, default="cloned")  # cloned, native
    audio_path = Column(String, nullable=True)  # path to reference audio file
    preview_url = Column(String, nullable=True)  # sample audio URL
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
