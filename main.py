# Build a minimal Instagram-like Flask app and zip it for the user
import os, textwrap, zipfile, json

base = "/mnt/data/mini_insta_flask"
os.makedirs(base, exist_ok=True)
for sub in ["templates", "static", "uploads"]:
    os.makedirs(os.path.join(base, sub), exist_ok=True)

files = {}

files["app.py"] = textwrap.dedent("""
import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    posts = db.relationship("Post", backref="author", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    comments = db.relationship("Comment", backref="post", lazy=True, cascade="all, delete-orphan")
    likes = db.relationship("Like", backref="post", lazy=True, cascade="all, delete-orphan")

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.before_first_request
def init_db():
    db.create_all()

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/")
def index():
    # Public feed: most recent first
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template("feed.html", posts=posts)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Usuario y contraseña son obligatorios.", "error")
            return redirect(url_for("register"))
        if User.query.filter_by(username=username).first():
            flash("Ese usuario ya existe.", "error")
            return redirect(url_for("register"))
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Cuenta creada. Inicia sesión.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Bienvenido, " + user.username, "success")
            return redirect(url_for("index"))
        flash("Credenciales inválidas.", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("index"))

@app.route("/new", methods=["GET", "POST"])
@login_required
def new_post():
    if request.method == "POST":
        caption = request.form.get("caption", "")
        file = request.files.get("image")
        if not file or file.filename == "":
            flash("Debes seleccionar una imagen.", "error")
            return redirect(url_for("new_post"))
        if not allowed_file(file.filename):
            flash("Formato no permitido. Usa png, jpg, jpeg, gif o webp.", "error")
            return redirect(url_for("new_post"))
        filename = secure_filename(f"{current_user.id}_{int(datetime.utcnow().timestamp())}_{file.filename}")
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(path)
        post = Post(image_filename=filename, caption=caption, author=current_user)
        db.session.add(post)
        db.session.commit()
        flash("Publicación creada.", "success")
        return redirect(url_for("index"))
    return render_template("new_post.html")

@app.route("/p/<int:post_id>", methods=["GET", "POST"])
def view_post(post_id):
    post = Post.query.get_or_404(post_id)
    if request.method == "POST":
        # add comment
        if not current_user.is_authenticated:
            abort(403)
        text = request.form.get("text", "").strip()
        if text:
            c = Comment(text=text, user_id=current_user.id, post_id=post.id)
            db.session.add(c)
            db.session.commit()
            flash("Comentario agregado.", "success")
        return redirect(url_for("view_post", post_id=post.id))
    liked = False
    if current_user.is_authenticated:
        liked = Like.query.filter_by(user_id=current_user.id, post_id=post.id).first() is not None
    return render_template("post.html", post=post, liked=liked)

@app.route("/like/<int:post_id>", methods=["POST"])
@login_required
def like(post_id):
    post = Post.query.get_or_404(post_id)
    existing = Like.query.filter_by(user_id=current_user.id, post_id=post.id).first()
    if existing:
        db.session.delete(existing)  # toggle unlike
        db.session.commit()
        flash("Ya no te gusta.", "info")
    else:
        like = Like(user_id=current_user.id, post_id=post.id)
        db.session.add(like)
        db.session.commit()
        flash("Te gusta esta publicación.", "success")
    return redirect(request.referrer or url_for("view_post", post_id=post.id))

@app.route("/u/<string:username>")
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).all()
    return render_template("profile.html", profile_user=user, posts=posts)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
""")

files["templates/base.html"] = textwrap.dedent("""
<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ title or 'MiniInsta' }}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
  </head>
  <body>
    <header class="topbar">
      <a class="brand" href="{{ url_for('index') }}">MiniInsta</a>
      <nav class="menu">
        {% if current_user.is_authenticated %}
          <a href="{{ url_for('new_post') }}">Nueva publicación</a>
          <a href="{{ url_for('profile', username=current_user.username) }}">Perfil</a>
          <a href="{{ url_for('logout') }}">Salir</a>
        {% else %}
          <a href="{{ url_for('login') }}">Entrar</a>
          <a href="{{ url_for('register') }}">Crear cuenta</a>
        {% endif %}
      </nav>
    </header>
    <main class="container">
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
          <ul class="flashes">
            {% for category, message in messages %}
              <li class="flash {{ category }}">{{ message }}</li>
            {% endfor %}
          </ul>
        {% endif %}
      {% endwith %}
      {% block content %}{% endblock %}
    </main>
    <footer class="footer">
      <p>Hecho con Flask · Esto es una demo educativa.</p>
    </footer>
  </body>
</html>
""")

files["templates/feed.html"] = textwrap.dedent("""
{% extends "base.html" %}
{% block content %}
  <h1>Feed</h1>
  {% if posts|length == 0 %}
    <p>No hay publicaciones aún. {% if current_user.is_authenticated %}<a href="{{ url_for('new_post') }}">Crea la primera</a>.{% endif %}</p>
  {% endif %}
  <div class="grid">
    {% for p in posts %}
      <article class="card">
        <a href="{{ url_for('view_post', post_id=p.id) }}">
          <img src="{{ url_for('uploaded_file', filename=p.image_filename) }}" alt="post image">
        </a>
        <div class="card-body">
          <div class="meta">
            <a href="{{ url_for('profile', username=p.author.username) }}">@{{ p.author.username }}</a>
            <span>· {{ p.created_at.strftime('%Y-%m-%d %H:%M') }}</span>
          </div>
          {% if p.caption %}<p>{{ p.caption }}</p>{% endif %}
          <form method="post" action="{{ url_for('like', post_id=p.id) }}">
            <button type="submit">❤️ {{ p.likes|length }}</button>
          </form>
          <a class="comments-link" href="{{ url_for('view_post', post_id=p.id) }}">
            Ver comentarios ({{ p.comments|length }})
          </a>
        </div>
      </article>
    {% endfor %}
  </div>
{% endblock %}
""")

files["templates/login.html"] = textwrap.dedent("""
{% extends "base.html" %}
{% block content %}
  <h1>Entrar</h1>
  <form method="post" class="form">
    <label>Usuario
      <input name="username" required>
    </label>
    <label>Contraseña
      <input name="password" type="password" required>
    </label>
    <button type="submit">Entrar</button>
  </form>
{% endblock %}
""")

files["templates/register.html"] = textwrap.dedent("""
{% extends "base.html" %}
{% block content %}
  <h1>Crear cuenta</h1>
  <form method="post" class="form">
    <label>Usuario
      <input name="username" required>
    </label>
    <label>Contraseña
      <input name="password" type="password" required>
    </label>
    <button type="submit">Registrarme</button>
  </form>
{% endblock %}
""")

files["templates/new_post.html"] = textwrap.dedent("""
{% extends "base.html" %}
{% block content %}
  <h1>Nueva publicación</h1>
  <form method="post" enctype="multipart/form-data" class="form">
    <label>Imagen
      <input type="file" name="image" accept="image/*" required>
    </label>
    <label>Descripción
      <textarea name="caption" rows="3" placeholder="Escribe un pie de foto..."></textarea>
    </label>
    <button type="submit">Publicar</button>
  </form>
{% endblock %}
""")

files["templates/profile.html"] = textwrap.dedent("""
{% extends "base.html" %}
{% block content %}
  <h1>Perfil de @{{ profile_user.username }}</h1>
  <p>Se unió el {{ profile_user.joined_at.strftime('%Y-%m-%d') }}</p>
  <h2>Publicaciones</h2>
  <div class="grid">
    {% for p in posts %}
      <article class="card">
        <a href="{{ url_for('view_post', post_id=p.id) }}">
          <img src="{{ url_for('uploaded_file', filename=p.image_filename) }}" alt="post image">
        </a>
      </article>
    {% else %}
      <p>Este usuario no tiene publicaciones.</p>
    {% endfor %}
  </div>
{% endblock %}
""")

files["templates/post.html"] = textwrap.dedent("""
{% extends "base.html" %}
{% block content %}
  <article class="post">
    <img class="hero" src="{{ url_for('uploaded_file', filename=post.image_filename) }}" alt="post image">
    <div class="post-body">
      <div class="meta">
        <a href="{{ url_for('profile', username=post.author.username) }}">@{{ post.author.username }}</a>
        <span>· {{ post.created_at.strftime('%Y-%m-%d %H:%M') }}</span>
      </div>
      {% if post.caption %}<p>{{ post.caption }}</p>{% endif %}
      <form method="post" action="{{ url_for('like', post_id=post.id) }}">
        <button type="submit">{{ '💔' if liked else '❤️' }} {{ post.likes|length }}</button>
      </form>
    </div>
  </article>

  <section class="comments">
    <h2>Comentarios ({{ post.comments|length }})</h2>
    {% for c in post.comments %}
      <div class="comment">
        <strong>#{{ loop.index }}</strong>
        <span>{{ c.text }}</span>
      </div>
    {% else %}
      <p>No hay comentarios aún.</p>
    {% endfor %}

    {% if current_user.is_authenticated %}
    <form method="post" class="form">
      <label>Escribe un comentario
        <textarea name="text" required rows="2"></textarea>
      </label>
      <button type="submit">Comentar</button>
    </form>
    {% else %}
      <p><a href="{{ url_for('login') }}">Inicia sesión</a> para comentar.</p>
    {% endif %}
  </section>
{% endblock %}
""")

files["static/style.css"] = textwrap.dedent("""
:root { --fg: #111; --bg: #fafafa; --muted:#666; --card:#fff; --border:#eaeaea; }
* { box-sizing: border-box; }
html, body { margin:0; padding:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--fg); }
a { color: inherit; text-decoration: none; }
.container { max-width: 900px; margin: 80px auto 40px; padding: 0 16px; }
.topbar { position: fixed; top:0; left:0; right:0; height: 56px; background: var(--card); border-bottom:1px solid var(--border); display:flex; align-items:center; justify-content:space-between; padding:0 16px; }
.brand { font-weight: 800; }
.menu a { margin-left: 12px; color:#0070f3; }
.flashes { list-style:none; padding:0; margin: 12px 0; }
.flash { padding:10px 12px; border:1px solid var(--border); border-radius:10px; background: #fff; }
.flash.error { border-color:#ff6b6b; }
.flash.success { border-color:#22c55e; }
.flash.info { border-color:#60a5fa; }
.grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap:16px; }
.card { background: var(--card); border:1px solid var(--border); border-radius:16px; overflow:hidden; }
.card img { width:100%; display:block; aspect-ratio: 1 / 1; object-fit: cover; }
.card-body { padding:12px; }
.meta { color: var(--muted); font-size: 14px; margin-bottom: 6px; display:flex; gap:8px; align-items:center;}
.form { display:grid; gap:12px; background: var(--card); border:1px solid var(--border); border-radius:16px; padding:16px; }
input, textarea, button { width:100%; padding:10px; border:1px solid var(--border); border-radius:10px; }
button { cursor:pointer; }
.post .hero { width:100%; border-radius:16px; border:1px solid var(--border); }
.post-body { padding: 12px 0; }
.comments { margin-top: 24px; background: var(--card); border:1px solid var(--border); border-radius:16px; padding:16px; }
.comment { padding:8px 0; border-bottom:1px dashed var(--border); }
.comment:last-child { border-bottom:0; }
.footer { text-align:center; color:var(--muted); padding:20px; }
""")

files["requirements.txt"] = textwrap.dedent("""
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
Werkzeug==3.0.1
""")

files[".gitignore"] = textwrap.dedent("""
__pycache__/
*.pyc
*.pyo
*.pyd
.env
.venv/
venv/
app.db
uploads/
.DS_Store
""")

