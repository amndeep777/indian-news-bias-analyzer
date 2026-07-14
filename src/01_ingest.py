from __future__ import annotations

import argparse
import time

import feedparser
import schedule

from common import FEED_SOURCES, REQUEST_HEADERS, article_text, connect_db, initialize_schema, parse_entry_datetime


def fetch_feed(source: str, url: str) -> list[dict[str, str | None]]:
    parsed = feedparser.parse(url, request_headers=REQUEST_HEADERS)
    records: list[dict[str, str | None]] = []
    for entry in parsed.entries:
        link = entry.get("link") or entry.get("id")
        if not link:
            continue
        records.append(
            {
                "source": source,
                "title": entry.get("title", "").strip(),
                "description": article_text(entry.get("summary") or entry.get("description"), None),
                "published_at": parse_entry_datetime(entry),
                "url": link.strip(),
            }
        )
    return records


def fetch_source_records(source: str, urls: tuple[str, ...]) -> list[dict[str, str | None]]:
    last_records: list[dict[str, str | None]] = []
    for url in urls:
        records = fetch_feed(source, url)
        if records:
            return records
        last_records = records
    return last_records


def ingest_once() -> dict[str, int]:
    connection = connect_db()
    initialize_schema(connection)

    inserted = 0
    per_source: dict[str, int] = {}
    try:
        for source, urls in FEED_SOURCES.items():
            records = fetch_source_records(source, urls)
            per_source[source] = len(records)
            for record in records:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO articles (source, title, description, published_at, url)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        record["source"],
                        record["title"],
                        record["description"],
                        record["published_at"],
                        record["url"],
                    ),
                )
                inserted += cursor.rowcount
        connection.commit()
    finally:
        connection.close()

    return {"inserted": inserted, **{f"fetched_{source.lower().replace(' ', '_')}": count for source, count in per_source.items()}}


def run_scheduler() -> None:
    ingest_once()
    schedule.every(6).hours.do(ingest_once)
    while True:
        schedule.run_pending()
        time.sleep(60)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest Indian news RSS feeds into SQLite.")
    parser.add_argument("--schedule", action="store_true", help="Keep the script running and ingest every 6 hours.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.schedule:
        run_scheduler()
    else:
        summary = ingest_once()
        print(summary)


if __name__ == "__main__":
    main()
