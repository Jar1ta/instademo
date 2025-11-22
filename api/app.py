from flask import Flask, render_template
import feedparser

app = Flask(__name__)

@app.route('/feed')
def feed():
    url = "https://www.nasa.gov/rss/dyn/breaking_news.rss"
    data = feedparser.parse(url)
    return render_template("feed.html", items=data.entries)

@app.route('/')
def home():
    return render_template("base.html", title="Inicio")
