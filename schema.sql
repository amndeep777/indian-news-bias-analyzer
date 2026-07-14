PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  published_at TEXT,
  url TEXT NOT NULL UNIQUE,
  topic_cluster TEXT,
  sentiment_score REAL,
  bias_score REAL
);

CREATE TABLE IF NOT EXISTS keywords (
  article_id INTEGER NOT NULL,
  keyword TEXT NOT NULL,
  freq INTEGER NOT NULL,
  PRIMARY KEY (article_id, keyword),
  FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bias_summary (
  source TEXT NOT NULL,
  topic TEXT NOT NULL,
  avg_sentiment REAL NOT NULL,
  avg_bias REAL NOT NULL,
  loaded_word_count INTEGER NOT NULL,
  article_count INTEGER NOT NULL,
  fetched_date TEXT NOT NULL,
  PRIMARY KEY (source, topic, fetched_date)
);
