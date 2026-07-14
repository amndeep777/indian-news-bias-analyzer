from __future__ import annotations

from collections import Counter
from typing import Iterable

from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from common import (
    article_keyword_counter,
    article_text,
    connect_db,
    fetch_articles_with_text,
    initialize_schema,
)


def build_documents(rows) -> tuple[list[int], list[str]]:
    article_ids: list[int] = []
    documents: list[str] = []
    for row in rows:
        article_ids.append(int(row["id"]))
        documents.append(article_text(row["title"], row["description"]))
    return article_ids, documents


def cluster_articles() -> dict[str, int]:
    connection = connect_db()
    initialize_schema(connection)

    rows = fetch_articles_with_text(connection)
    if len(rows) < 2:
        connection.close()
        return {"articles_clustered": 0, "clusters": 0}

    article_ids, documents = build_documents(rows)

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=4000, stop_words="english")
    matrix = vectorizer.fit_transform(documents)
    k = min(max(2, int(len(documents) ** 0.5)), 15, len(documents))

    model = KMeans(n_clusters=k, random_state=42, n_init="auto")
    cluster_ids = model.fit_predict(matrix)
    feature_names = vectorizer.get_feature_names_out()

    topic_labels: dict[int, str] = {}
    for cluster_id, centroid in enumerate(model.cluster_centers_):
        top_indices = centroid.argsort()[-3:][::-1]
        top_terms = [feature_names[index].replace(" ", "-") for index in top_indices if centroid[index] > 0]
        topic_labels[cluster_id] = "-".join(top_terms) if top_terms else f"topic-{cluster_id + 1}"

    keyword_rows: list[tuple[int, str, int]] = []
    for article_id, row, cluster_id in zip(article_ids, rows, cluster_ids):
        label = topic_labels[int(cluster_id)]
        connection.execute("UPDATE articles SET topic_cluster = ? WHERE id = ?", (label, article_id))
        counter = article_keyword_counter(article_text(row["title"], row["description"]))
        keyword_rows.extend((article_id, keyword, int(freq)) for keyword, freq in counter.most_common(15))

    connection.execute("DELETE FROM keywords")
    connection.executemany(
        """
        INSERT INTO keywords (article_id, keyword, freq)
        VALUES (?, ?, ?)
        ON CONFLICT(article_id, keyword) DO UPDATE SET freq = excluded.freq
        """,
        keyword_rows,
    )
    connection.commit()
    connection.close()

    return {"articles_clustered": len(article_ids), "clusters": len(set(cluster_ids))}


if __name__ == "__main__":
    print(cluster_articles())
