from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from git import Repo, InvalidGitRepositoryError

from common import REPORTS_DIR, connect_db, initialize_schema, today_iso_date


def build_report_markdown() -> str:
    connection = connect_db()
    initialize_schema(connection)

    today = today_iso_date()
    rows = connection.execute(
        """
        SELECT source, topic, avg_sentiment, avg_bias, loaded_word_count, article_count
        FROM bias_summary
        WHERE fetched_date = ?
        ORDER BY avg_bias DESC, ABS(avg_sentiment) DESC
        """,
        (today,),
    ).fetchall()

    if not rows:
        rows = connection.execute(
            """
            SELECT source, topic_cluster AS topic, AVG(sentiment_score) AS avg_sentiment,
                 AVG(bias_score) AS avg_bias, 0 AS loaded_word_count, COUNT(*) AS article_count
            FROM articles
            WHERE topic_cluster IS NOT NULL
            GROUP BY source, topic_cluster
            ORDER BY AVG(bias_score) DESC
            LIMIT 10
            """
        ).fetchall()

    if rows:
        top_row = rows[0]
        headline = (
            f"Yesterday's most biased topic was {top_row['topic']} — {top_row['source']} scored "
            f"{float(top_row['avg_bias']):+.2f} bias with sentiment {float(top_row['avg_sentiment']):+.2f}."
        )
    else:
        headline = "No aggregated bias data is available yet. Run ingestion, clustering, and sentiment scoring first."

    report_lines = [
        f"# Daily Bias Report - {today}",
        "",
        headline,
        "",
        "## Top outlet/topic combinations",
    ]

    for row in rows[:10]:
        report_lines.append(
            f"- {row['source']} | {row['topic']} | bias {float(row['avg_bias']):+.2f} | sentiment {float(row['avg_sentiment']):+.2f} | articles {int(row['article_count'])}"
        )

    connection.close()
    return "\n".join(report_lines).strip() + "\n"


def maybe_commit_report(report_path: Path) -> None:
    try:
        repo = Repo(str(report_path.parent.parent))
    except InvalidGitRepositoryError:
        return

    try:
        relative_path = report_path.relative_to(Path(repo.working_tree_dir))
        repo.git.add(str(relative_path))
        if repo.is_dirty(index=True, working_tree=False, untracked_files=False):
            repo.index.commit(f"Add daily report {report_path.stem}")
    except Exception:
        return


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_markdown = build_report_markdown()
    report_path = REPORTS_DIR / f"{today_iso_date()}.md"
    report_path.write_text(report_markdown, encoding="utf-8")
    maybe_commit_report(report_path)
    print(report_path)


if __name__ == "__main__":
    main()
