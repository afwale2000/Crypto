# models.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_miner = Column(Boolean, default=True)
    wallet = relationship("Wallet", uselist=False, back_populates="user")

class Wallet(Base):
    __tablename__ = "wallets"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    address = Column(String, unique=True)            # simulated address
    balance = Column(Float, default=0.0)
    user = relationship("User", back_populates="wallet")

class MinerSession(Base):
    __tablename__ = "miner_sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    started_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    active = Column(Boolean, default=True)
    shares = Column(Integer, default=0)  # number of shares submitted in session

class Share(Base):
    __tablename__ = "shares"
    id = Column(Integer, primary_key=True)
    miner_session_id = Column(Integer, ForeignKey("miner_sessions.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    weight = Column(Float, default=1.0)

class Payout(Base):
    __tablename__ = "payouts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    txid = Column(String, nullable=True)
