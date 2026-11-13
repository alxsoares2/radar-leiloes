import hmac
import os
import json
import time

import requests
from flask import Flask, abort, jsonify, redirect, render_template_string, request, send_from_directory, session

from cloud import Supabase
from radar import ROOT

supabase_url = os.environ["SUPABASE_URL"].rstrip("/")

app = Flask(__name__, static_folder=None)
app.config.update(
    SECRET_KEY=os.environ["RADAR_SESSION_SECRET"],
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=4096,
)
allowed_email = os.environ["RADAR_OWNER_EMAIL"].strip().lower()
auth_key = os.environ["SUPABASE_PUBLISHABLE_KEY"]
if not allowed_email or not auth_key or len(app.secret_key) < 32:
    raise RuntimeError("Configure o e-mail do proprietário, a chave pública e um segredo de sessão de 32 caracteres ou mais.")

LOGIN = """<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Radar de Leilões</title>
<style>body{font:16px Arial;background:#f1f4ee;color:#143b30;max-width:360px;margin:12vh auto;padding:20px}
label,input{display:block}input,button{box-sizing:border-box;width:100%;padding:11px;margin:8px 0 16px}
button{background:#143b30;color:white;border:0;border-radius:8px}</style><h1>Radar de Leilões</h1>
{% if error %}<p role="alert">{{ error }}</p>{% endif %}
<form method="post"><label>E-mail<input name="email" type="email" autocomplete="username" required></label>
<label>Senha<input name="password" type="password" autocomplete="current-password" required></label><button>Entrar</button></form></html>"""


@app.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template_string(LOGIN, error=None)
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    if email == allowed_email and password and len(password) <= 512:
        try:
            response = requests.post(
                f"{supabase_url}/auth/v1/token", params={"grant_type": "password"},
                headers={"apikey": auth_key}, json={"email": email, "password": password}, timeout=12,
            )
            if response.ok:
                user = response.json().get("user", {})
                account = user.get("email", "").lower()
                token = response.json().get("access_token")
                if token and user.get("id") and hmac.compare_digest(account.encode(), allowed_email.encode()):
                    session.clear()
                    session["owner"] = account
                    session["token"] = token
                    session["expires"] = int(time.time()) + min(3600, int(response.json().get("expires_in", 3600)))
                    return redirect("/")
        except (requests.RequestException, ValueError):
            return render_template_string(LOGIN, error="Autenticação indisponível. Tente novamente."), 503
    return render_template_string(LOGIN, error="E-mail ou senha inválidos."), 401


@app.get("/health")
def health():
    return "OK"


@app.get("/")
@app.get("/<path:filename>")
def panel(filename="index.html"):
    if session.get("owner") != allowed_email or not session.get("token") or session.get("expires", 0) <= time.time():
        if filename == "api/lots":
            abort(401)
        return redirect("/login")
    if filename == "api/lots":
        try:
            database = Supabase(supabase_url, auth_key)
            database.headers["Authorization"] = "Bearer " + session["token"]
            data = database.read()
            if data is None:
                data = json.loads((ROOT / "seed.json").read_text(encoding="utf-8"))
            return jsonify({**data, "manualRefresh": False})
        except (requests.RequestException, RuntimeError):
            return jsonify(error="Base temporariamente indisponível."), 503
    if filename not in {"index.html", "app.js", "style.css", "data.js"}:
        abort(404)
    return send_from_directory(ROOT / "dist", filename)

