from __future__ import annotations

import os
import re
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable

import sqlite3

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
OUTPUTS_DIR = ROOT / "outputs"
SCHEMA_PATH = ROOT / "schema.sql"

SQLITE_PATH = Path(os.getenv("SQLITE_PATH", str(DATA_DIR / "news_bias.db"))).expanduser()

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Cache-Control": "no-cache",
}

FEED_SOURCES = {
    "Times of India": (
        "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
        "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms",
    ),
    "NDTV": ("https://feeds.feedburner.com/ndtvnews-top-stories",),
    "The Hindu": ("https://www.thehindu.com/news/national/feeder/default.rss",),
    "Indian Express": ("https://indianexpress.com/feed/",),
}

LOADED_WORDS = {
    "accused",
    "alleged",
    "angry",
    "blasted",
    "bombshell",
    "chaos",
    "collapsed",
    "controversial",
    "crisis",
    "damning",
    "demanded",
    "denounced",
    "disaster",
    "explosive",
    "fury",
    "hailed",
    "harsh",
    "horrific",
    "infuriated",
    "outrage",
    "praised",
    "ridiculed",
    "scandal",
    "slammed",
    "storm",
    "struck",
    "sweeping",
    "tumult",
    "warned",
    "wins",
    "woeful",
}

TOKEN_RE = re.compile(r"[a-z][a-z0-9]+")
WORD_RE_TEMPLATE = r"\b{word}\b"


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


class DatabaseConnection:
    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")

    def cursor(self):
        return CursorProxy(self._connection.cursor())

    def execute(self, query: str, params: tuple | list | None = None):
        cursor = self.cursor()
        cursor.execute(query, params or ())
        return cursor

    def executemany(self, query: str, params: list[tuple] | list[list]):
        cursor = self.cursor()
        cursor.executemany(query, params)
        return cursor

    def executescript(self, script: str):
        self._connection.executescript(script)

    def commit(self) -> None:
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()


class CursorProxy:
    def __init__(self, cursor):
        self._cursor = cursor

    @staticmethod
    def _translate_query(query: str) -> str:
        return query.replace("%s", "?")

    def execute(self, query: str, params: tuple | list | None = None):
        return self._cursor.execute(self._translate_query(query), params or ())

    def executemany(self, query: str, params):
        return self._cursor.executemany(self._translate_query(query), params)

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, item):
        return getattr(self._cursor, item)


def connect_db() -> DatabaseConnection:
    ensure_directories()
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(SQLITE_PATH))
    return DatabaseConnection(connection)


def initialize_schema(connection: DatabaseConnection) -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    connection.executescript(schema_sql)
    connection.commit()


def clean_text(*parts: str | None) -> str:
    values = [part.strip() for part in parts if part and part.strip()]
    return " ".join(values)


def article_text(title: str | None, description: str | None) -> str:
    return clean_text(title, description)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_entry_datetime(entry: dict) -> str | None:
    for field in ("published_parsed", "updated_parsed"):
        value = entry.get(field)
        if value:
            dt = datetime(*value[:6], tzinfo=timezone.utc)
            return dt.isoformat()

    for field in ("published", "updated"):
        value = entry.get(field)
        if value:
            try:
                dt = parsedate_to_datetime(value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).isoformat()
            except (TypeError, ValueError):
                continue
    return None


def tokenise(text: str | None) -> list[str]:
    if not text:
        return []
    lowered = text.lower()
    return TOKEN_RE.findall(lowered)


def count_loaded_words(text: str | None) -> int:
    tokens = tokenise(text)
    return sum(token in LOADED_WORDS for token in tokens)


def article_keyword_counter(text: str | None) -> Counter[str]:
    tokens = [token for token in tokenise(text) if len(token) >= 4 and token not in LOADED_WORDS]
    stop_words = {
        "about",
        "after",
        "also",
        "amid",
        "area",
        "being",
        "been",
        "before",
        "between",
        "could",
        "from",
        "have",
        "into",
        "more",
        "most",
        "news",
        "over",
        "said",
        "says",
        "that",
        "their",
        "there",
        "this",
        "with",
        "your",
        "they",
        "what",
        "when",
        "where",
        "which",
        "while",
        "will",
        "would",
        "today",
        "yesterday",
    }
    filtered = [token for token in tokens if token not in stop_words]
    return Counter(filtered)


def fetch_all_articles(connection: DatabaseConnection) -> list[dict]:
    return list(connection.execute("SELECT * FROM articles ORDER BY published_at DESC, id DESC"))


def fetch_articles_with_text(connection: DatabaseConnection) -> list[dict]:
    return list(
        connection.execute(
            """
            SELECT id, source, title, description, published_at, url, topic_cluster, sentiment_score, bias_score
            FROM articles
            WHERE COALESCE(title, '') <> ''
            ORDER BY published_at DESC, id DESC
            """
        )
    )


def today_iso_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def grouped(iterable: Iterable, size: int) -> list[list]:
    batch: list = []
    result: list[list] = []
    for item in iterable:
        batch.append(item)
        if len(batch) == size:
            result.append(batch)
            batch = []
    if batch:
        result.append(batch)
    return result
