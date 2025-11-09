// static/client.js
const socket = io();

// UI elements
const el = {
  reg_username: document.getElementById("reg_username"),
  reg_password: document.getElementById("reg_password"),
  btnRegister: document.getElementById("btnRegister"),
  login_username: document.getElementById("login_username"),
  login_password: document.getElementById("login_password"),
  btnLogin: document.getElementById("btnLogin"),
  meArea: document.getElementById("meArea"),
  authForms: document.getElementById("authForms"),
  me_username: document.getElementById("me_username"),
  me_wallet: document.getElementById("me_wallet"),
  me_balance: document.getElementById("me_balance"),
  btnStartMining: document.getElementById("btnStartMining"),
  btnStopMining: document.getElementById("btnStopMining"),
  miner_session_id: document.getElementById("miner_session_id"),
  miners_count: document.getElementById("miners_count"),
  total_shares: document.getElementById("total_shares"),
  btnSubmitShare: document.getElementById("btnSubmitShare"),
  btnAutoMine: document.getElementById("btnAutoMine"),
  btnStopAuto: document.getElementById("btnStopAuto"),
  chat: document.getElementById("chat"),
  chat_input: document.getElementById("chat_input"),
  btnSendChat: document.getElementById("btnSendChat"),
  balances: document.getElementById("balances"),
  payout_amount: document.getElementById("payout_amount"),
  btnPayout: document.getElementById("btnPayout"),
  payout_result: document.getElementById("payout_result")
};

let miner_session_id = null;
let me_username = null;
let autominer = null;

// helpers
function showMsg(text) {
  const d = document.createElement("div");
  d.textContent = text;
  el.chat.appendChild(d);
  el.chat.scrollTop = el.chat.scrollHeight;
}

function refreshMe() {
  fetch("/api/me").then(r => r.json()).then(js => {
    if (js.logged_in) {
      el.authForms.style.display = "none";
      el.meArea.style.display = "block";
      el.me_username.textContent = js.user.username;
      el.me_wallet.textContent = js.wallet.address;
      el.me_balance.textContent = js.wallet.balance.toFixed(6);
      me_username = js.user.username;
      el.btnSubmitShare.disabled = false;
      el.btnAutoMine.disabled = false;
      el.btnSendChat.disabled = false;
    } else {
      el.authForms.style.display = "block";
      el.meArea.style.display = "none";
      me_username = null;
      el.btnSubmitShare.disabled = true;
      el.btnAutoMine.disabled = true;
      el.btnSendChat.disabled = true;
    }
  });
}

// register
el.btnRegister.onclick = () => {
  fetch("/api/register", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({username: el.reg_username.value, password: el.reg_password.value})
  }).then(r => r.json()).then(js => {
    if (js.error) alert("Error: " + js.error);
    else {
      alert("Registered. Now login.");
      el.login_username.value = el.reg_username.value;
    }
  });
};

// login
el.btnLogin.onclick = () => {
  fetch("/api/login", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({username: el.login_username.value, password: el.login_password.value})
  }).then(r => r.json()).then(js => {
    if (js.error) alert("Error: " + js.error);
    else {
      refreshMe();
    }
  });
};

// start mining (join)
el.btnStartMining.onclick = () => {
  if (!me_username) { alert("Login first"); return; }
  socket.emit("join_miner", {username: me_username});
};

el.btnStopMining.onclick = () => {
  if (!miner_session_id) return;
  socket.emit("leave_miner", {miner_session_id});
  miner_session_id = null;
  el.miner_session_id.textContent = "-";
  el.btnStopMining.style.display = "none";
  el.btnStartMining.style.display = "inline-block";
  el.btnSubmitShare.disabled = true;
  el.btnAutoMine.disabled = true;
};

// submit one share
el.btnSubmitShare.onclick = () => {
  if (!miner_session_id) { alert("Start mining first"); return; }
  socket.emit("share", {miner_session_id});
};

// auto mine every 3s
el.btnAutoMine.onclick = () => {
  if (!miner_session_id) { alert("Start mining first"); return; }
  el.btnAutoMine.style.display = "none";
  el.btnStopAuto.style.display = "inline-block";
  autominer = setInterval(() => {
    socket.emit("share", {miner_session_id});
    socket.emit("heartbeat", {miner_session_id});
  }, 3000);
};

el.btnStopAuto.onclick = () => {
  clearInterval(autominer);
  autominer = null;
  el.btnAutoMine.style.display = "inline-block";
  el.btnStopAuto.style.display = "none";
};

// chat
el.btnSendChat.onclick = () => {
  if (!me_username) { alert("Login first"); return; }
  const msg = el.chat_input.value.trim();
  if (!msg) return;
  socket.emit("chat", {username: me_username, message: msg});
  el.chat_input.value = "";
};

// payout
el.btnPayout.onclick = () => {
  const amt = parseFloat(el.payout_amount.value);
  if (!amt || amt <= 0) { alert("Enter a valid amount"); return; }
  fetch("/api/payout", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({total_reward: amt})
  }).then(r => r.json()).then(js => {
    if (js.error) el.payout_result.textContent = "Error: " + js.error;
    else el.payout_result.textContent = "Payout done: " + JSON.stringify(js.payouts);
  });
};

// socket handlers
socket.on("hello", d => console.log("socket hello", d));
socket.on("joined", d => {
  miner_session_id = d.miner_session_id;
  el.miner_session_id.textContent = miner_session_id;
  el.btnStopMining.style.display = "inline-block";
  el.btnStartMining.style.display = "none";
  el.btnSubmitShare.disabled = false;
  el.btnAutoMine.disabled = false;
  showMsg("Joined miner session: " + miner_session_id);
});
socket.on("miners_count", d => {
  el.miners_count.textContent = d.count;
});
socket.on("token_update", d => {
  el.total_shares.textContent = d.total_shares;
});
socket.on("chat_message", d => {
  const node = document.createElement("div");
  node.className = "msg";
  node.innerHTML = "<b>" + d.username + "</b>: " + d.message + " <span class='small'>(" + new Date(d.ts).toLocaleTimeString() + ")</span>";
  el.chat.appendChild(node);
  el.chat.scrollTop = el.chat.scrollHeight;
});
socket.on("payouts", d => {
  showMsg("Payouts: " + JSON.stringify(d.payouts));
});
socket.on("balances", d => {
  // render balances
  el.balances.innerHTML = "";
  d.balances.forEach(b => {
    const rr = document.createElement("div");
    rr.textContent = "user_id " + b.user_id + " — " + parseFloat(b.balance).toFixed(6);
    el.balances.appendChild(rr);
  });
  // refresh my balance display
  refreshMe();
});

// initial check
refreshMe();

// heartbeat to server every 25s to keep sessions alive if active
setInterval(() => {
  if (miner_session_id) socket.emit("heartbeat", {miner_session_id});
}, 25000);
