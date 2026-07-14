from __future__ import annotations

import json
from collections import Counter, defaultdict
from itertools import combinations

from common import OUTPUTS_DIR, connect_db, initialize_schema


def top_topic_clusters(connection, limit: int = 5) -> list[str]:
    rows = connection.execute(
        """
        SELECT COALESCE(topic_cluster, 'unclustered') AS topic, COUNT(*) AS article_count
        FROM articles
        GROUP BY COALESCE(topic_cluster, 'unclustered')
        ORDER BY article_count DESC, topic ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [str(row["topic"]) for row in rows]


def keyword_rows_for_topic(connection, topic: str):
    return connection.execute(
        """
        SELECT a.source, a.topic_cluster AS topic, k.keyword, SUM(k.freq) AS freq
        FROM articles a
        JOIN keywords k ON a.id = k.article_id
        WHERE COALESCE(a.topic_cluster, 'unclustered') = ?
        GROUP BY a.source, a.topic_cluster, k.keyword
        ORDER BY freq DESC, k.keyword ASC
        """,
        (topic,),
    ).fetchall()


def analyse_framing() -> dict[str, object]:
    connection = connect_db()
    initialize_schema(connection)
    topics = top_topic_clusters(connection)

    result: dict[str, object] = {"topics": []}
    report_lines = ["# Framing analysis", ""]

    for topic in topics:
        rows = keyword_rows_for_topic(connection, topic)
        by_source: dict[str, Counter[str]] = defaultdict(Counter)
        for row in rows:
            by_source[str(row["source"])][str(row["keyword"])] += int(row["freq"])

        source_keywords = {
            source: [keyword for keyword, _ in counter.most_common(10)]
            for source, counter in by_source.items()
        }

        overlap_matrix: dict[str, dict[str, float]] = {}
        for left, right in combinations(sorted(source_keywords), 2):
            left_set = set(source_keywords[left])
            right_set = set(source_keywords[right])
            union = left_set | right_set
            overlap = len(left_set & right_set) / len(union) if union else 0.0
            overlap_matrix.setdefault(left, {})[right] = round(overlap, 3)
            overlap_matrix.setdefault(right, {})[left] = round(overlap, 3)

        result["topics"].append(
            {
                "topic": topic,
                "sources": {
                    source: {
                        "top_keywords": keywords,
                    }
                    for source, keywords in source_keywords.items()
                },
                "keyword_overlap": overlap_matrix,
            }
        )

        report_lines.append(f"## {topic}")
        for source, keywords in sorted(source_keywords.items()):
            report_lines.append(f"- {source}: {', '.join(keywords) if keywords else 'no keywords found'}")
        if overlap_matrix:
            report_lines.append("- Pairwise overlap:")
            for source, overlaps in sorted(overlap_matrix.items()):
                formatted = ", ".join(f"{other}: {score:.2f}" for other, score in sorted(overlaps.items()))
                report_lines.append(f"  - {source}: {formatted}")
        report_lines.append("")

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUTS_DIR / "framing_analysis.md").write_text("\n".join(report_lines).strip() + "\n", encoding="utf-8")
    (OUTPUTS_DIR / "framing_analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    connection.close()
    return result


if __name__ == "__main__":
    print(analyse_framing())
