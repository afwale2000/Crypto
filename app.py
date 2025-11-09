# app.py
import os
import uuid
import datetime
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash
from models import Base, User, Wallet, MinerSession, Share, Payout

# ----- Configuration -----
DB_URL = os.environ.get("DATABASE_URL", "sqlite:///pool.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-prod")

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ----- Database setup -----
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)
DBSession = sessionmaker(bind=engine)

# ----- Helpers -----
def create_wallet_address():
    return "SIM-" + uuid.uuid4().hex[:16]

def get_active_miner_sessions(s):
    # returns list of active MinerSession objects
    return s.query(MinerSession).filter_by(active=True).all()

def get_miners_count(s):
    # consider a session active if last_seen within 60s
    threshold = datetime.datetime.utcnow() - datetime.timedelta(seconds=60)
    # mark inactive ones
    for ms in s.query(MinerSession).filter(MinerSession.last_seen < threshold, MinerSession.active == True).all():
        ms.active = False
        s.add(ms)
    s.commit()
    return s.query(MinerSession).filter_by(active=True).count()

# ----- HTTP Routes -----
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    if not username or not password:
        return jsonify({"error":"username and password required"}), 400
    s = DBSession()
    if s.query(User).filter_by(username=username).first():
        return jsonify({"error":"username exists"}), 400
    user = User(username=username, password_hash=generate_password_hash(password), is_miner=True)
    s.add(user); s.commit()
    wallet = Wallet(user_id=user.id, address=create_wallet_address(), balance=0.0)
    s.add(wallet); s.commit()
    return jsonify({"user_id": user.id, "wallet_address": wallet.address})

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    s = DBSession()
    user = s.query(User).filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error":"invalid credentials"}), 401
    # SIMPLE session for demo (not production-grade)
    session['user_id'] = user.id
    session['username'] = user.username
    return jsonify({"user_id": user.id, "username": user.username})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok":True})

@app.route("/api/me")
def api_me():
    uid = session.get('user_id')
    s = DBSession()
    if not uid:
        return jsonify({"logged_in": False})
    user = s.query(User).get(uid)
    wallet = s.query(Wallet).filter_by(user_id=uid).first()
    return jsonify({"logged_in": True, "user": {"id": user.id, "username": user.username}, "wallet": {"address": wallet.address, "balance": wallet.balance}})

@app.route("/api/payout", methods=["POST"])
def api_payout():
    """
    Admin-style endpoint (no auth in demo) to distribute `total_reward` proportionally
    Request JSON: {"total_reward": 100.0}
    """
    data = request.json or {}
    total_reward = float(data.get("total_reward", 0.0))
    if total_reward <= 0:
        return jsonify({"error":"invalid total_reward"}), 400
    s = DBSession()
    active_sessions = get_active_miner_sessions(s)
    total_shares = sum(ms.shares for ms in active_sessions) or 0
    payouts = []
    if total_shares == 0:
        return jsonify({"error":"no shares to pay out"}), 400
    for ms in active_sessions:
        share_frac = (ms.shares / total_shares) if total_shares > 0 else 0
        amount = total_reward * share_frac
        wallet = s.query(Wallet).filter_by(user_id=ms.user_id).first()
        wallet.balance += amount
        s.add(Payout(user_id=ms.user_id, amount=amount))
        payouts.append({"user_id": ms.user_id, "amount": round(amount, 8)})
        ms.shares = 0  # reset shares for next period
        s.add(ms)
        s.add(wallet)
    s.commit()
    # Broadcast updates
    balances = [{"user_id": w.user_id, "balance": w.balance} for w in s.query(Wallet).all()]
    socketio.emit("payouts", {"payouts": payouts}, room="pool")
    socketio.emit("balances", {"balances": balances}, room="pool")
    return jsonify({"payouts": payouts})

# ----- Socket.IO events -----
@socketio.on("connect")
def on_connect():
    emit("hello", {"msg":"connected", "ts": str(datetime.datetime.utcnow())})

@socketio.on("join_miner")
def on_join_miner(data):
    username = data.get("username")
    if not username:
        emit("error", {"msg":"username required"})
        return
    s = DBSession()
    user = s.query(User).filter_by(username=username).first()
    if not user:
        emit("error", {"msg":"unknown user"})
        return
    # Create a miner session record
    ms = MinerSession(user_id=user.id, started_at=datetime.datetime.utcnow(), last_seen=datetime.datetime.utcnow(), active=True)
    s.add(ms); s.commit()
    join_room("pool")
    miners_count = get_miners_count(s)
    emit("joined", {"miner_session_id": ms.id, "user_id": user.id, "username": user.username})
    socketio.emit("miners_count", {"count": miners_count}, room="pool")

@socketio.on("heartbeat")
def on_heartbeat(data):
    msid = data.get("miner_session_id")
    s = DBSession()
    ms = s.query(MinerSession).get(msid)
    if not ms or not ms.active:
        emit("error", {"msg":"invalid session"})
        return
    ms.last_seen = datetime.datetime.utcnow()
    s.add(ms); s.commit()
    # occasionally broadcast miner count
    miners_count = get_miners_count(s)
    socketio.emit("miners_count", {"count": miners_count}, room="pool")

@socketio.on("share")
def on_share(data):
    """
    Miner submits one share (weight optional). This simulates mining activity.
    """
    msid = data.get("miner_session_id")
    weight = float(data.get("weight", 1.0))
    s = DBSession()
    ms = s.query(MinerSession).get(msid)
    if not ms or not ms.active:
        emit("error", {"msg":"invalid session"})
        return
    # increment session shares and record Share
    ms.shares += 1
    ms.last_seen = datetime.datetime.utcnow()
    s.add(ms)
    s.add(Share(miner_session_id=msid, weight=weight))
    s.commit()
    total_shares = sum(m.shares for m in s.query(MinerSession).filter_by(active=True).all())
    socketio.emit("token_update", {"total_shares": total_shares}, room="pool")

@socketio.on("chat")
def on_chat(data):
    # data: {username, message}
    msg = {"username": data.get("username"), "message": data.get("message"), "ts": str(datetime.datetime.utcnow())}
    socketio.emit("chat_message", msg, room="pool")

@socketio.on("leave_miner")
def on_leave(data):
    msid = data.get("miner_session_id")
    s = DBSession()
    ms = s.query(MinerSession).get(msid)
    if ms:
        ms.active = False
        s.add(ms); s.commit()
    leave_room("pool")
    miners_count = get_miners_count(s)
    socketio.emit("miners_count", {"count": miners_count}, room="pool")

# ----- Run -----
if __name__ == "__main__":
    # For demo use eventlet
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
