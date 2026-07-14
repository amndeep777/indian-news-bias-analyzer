from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from common import article_text, connect_db, count_loaded_words, initialize_schema, today_iso_date


@dataclass
class ArticleScore:
    article_id: int
    source: str
    topic: str
    sentiment: float
    bias: float
    loaded_words: int


def sentiment_for_text(analyzer: SentimentIntensityAnalyzer, text: str) -> float:
    return float(analyzer.polarity_scores(text)["compound"])


def score_articles() -> dict[str, int]:
    connection = connect_db()
    initialize_schema(connection)
    analyzer = SentimentIntensityAnalyzer()

    rows = list(
        connection.execute(
            """
            SELECT id, source, title, description, COALESCE(topic_cluster, 'unclustered') AS topic_cluster
            FROM articles
            ORDER BY published_at DESC, id DESC
            """
        )
    )

    scored_rows: list[ArticleScore] = []
    for row in rows:
        text = article_text(row["title"], row["description"])
        if not text:
            continue
        sentiment = sentiment_for_text(analyzer, text)
        loaded_words = count_loaded_words(text)
        token_count = max(len(text.split()), 1)
        loaded_ratio = loaded_words / token_count
        bias = abs(sentiment) * (1.0 + loaded_ratio)
        connection.execute(
            """
            UPDATE articles
            SET sentiment_score = ?, bias_score = ?
            WHERE id = ?
            """,
            (sentiment, bias, row["id"]),
        )
        scored_rows.append(
            ArticleScore(
                article_id=int(row["id"]),
                source=str(row["source"]),
                topic=str(row["topic_cluster"]),
                sentiment=sentiment,
                bias=bias,
                loaded_words=loaded_words,
            )
        )

    fetched_date = today_iso_date()
    aggregated: dict[tuple[str, str], list[ArticleScore]] = defaultdict(list)
    for score in scored_rows:
        aggregated[(score.source, score.topic)].append(score)

    for (source, topic), items in aggregated.items():
        avg_sentiment = mean(item.sentiment for item in items)
        avg_bias = mean(item.bias for item in items)
        total_loaded = sum(item.loaded_words for item in items)
        article_count = len(items)
        connection.execute(
            """
            INSERT INTO bias_summary (
              source, topic, avg_sentiment, avg_bias, loaded_word_count, article_count, fetched_date
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(source, topic, fetched_date) DO UPDATE SET
                                avg_sentiment = excluded.avg_sentiment,
                                avg_bias = excluded.avg_bias,
                                loaded_word_count = excluded.loaded_word_count,
                                article_count = excluded.article_count
            """,
                        (source, topic, avg_sentiment, avg_bias, total_loaded, article_count, fetched_date),
        )

    connection.commit()
    connection.close()
    return {"scored_articles": len(scored_rows), "summaries_written": len(aggregated)}


if __name__ == "__main__":
    print(score_articles())
