from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from common import OUTPUTS_DIR, connect_db, initialize_schema, today_iso_date


def load_summary() -> pd.DataFrame:
    connection = connect_db()
    initialize_schema(connection)
    rows = connection.execute(
        """
        SELECT source, topic, avg_sentiment, avg_bias, loaded_word_count, article_count, fetched_date
        FROM bias_summary
        ORDER BY fetched_date DESC, avg_bias DESC, article_count DESC
        LIMIT 30
        """
    ).fetchall()
    connection.close()
    return pd.DataFrame.from_records([dict(row) for row in rows])


def build_dashboard(summary: pd.DataFrame) -> tuple[Path, Path]:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    png_path = OUTPUTS_DIR / "bias_dashboard.png"
    md_path = OUTPUTS_DIR / "bias_dashboard.md"

    if summary.empty:
        md_path.write_text(
            "# Bias Dashboard\n\nNo bias summary data is available yet. Run the pipeline first.\n",
            encoding="utf-8",
        )
        return png_path, md_path

    summary = summary.copy()
    summary["combo"] = summary["source"].astype(str) + " | " + summary["topic"].astype(str)
    top_bias = summary.sort_values("avg_bias", ascending=False).head(12)
    by_source = summary.groupby("source", as_index=False)[["avg_bias", "article_count"]].mean().sort_values(
        "avg_bias", ascending=False
    )

    sns.set_theme(style="whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(18, 8))
    fig.suptitle(f"Indian News Bias Dashboard — {today_iso_date()}", fontsize=16, fontweight="bold")

    sns.barplot(data=top_bias, y="combo", x="avg_bias", hue="combo", ax=axes[0], palette="rocket", legend=False)
    axes[0].set_title("Top outlet/topic bias scores")
    axes[0].set_xlabel("Average bias")
    axes[0].set_ylabel("")

    sns.barplot(data=by_source, y="source", x="avg_bias", hue="source", ax=axes[1], palette="viridis", legend=False)
    axes[1].set_title("Average bias by outlet")
    axes[1].set_xlabel("Average bias")
    axes[1].set_ylabel("")

    plt.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(png_path, dpi=160, bbox_inches="tight")
    plt.close(fig)

    top_table = top_bias[["source", "topic", "avg_sentiment", "avg_bias", "loaded_word_count", "article_count"]].copy()
    top_table["avg_sentiment"] = top_table["avg_sentiment"].map(lambda value: f"{float(value):+.3f}")
    top_table["avg_bias"] = top_table["avg_bias"].map(lambda value: f"{float(value):+.3f}")

    header = "| " + " | ".join(top_table.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(top_table.columns)) + " |"
    rows = ["| " + " | ".join(str(value) for value in row) + " |" for row in top_table.itertuples(index=False, name=None)]

    markdown = [
        "# Bias Dashboard",
        "",
        f"Generated on {today_iso_date()}.",
        "",
        f"![Bias dashboard]({png_path.name})",
        "",
        "## Top topics",
        "",
        header,
        separator,
        *rows,
        "",
    ]
    md_path.write_text("\n".join(markdown), encoding="utf-8")
    return png_path, md_path


def main() -> None:
    summary = load_summary()
    png_path, md_path = build_dashboard(summary)
    print(png_path)
    print(md_path)


if __name__ == "__main__":
    main()