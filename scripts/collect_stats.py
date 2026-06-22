#!/usr/bin/env python3
"""Collect note.com article stats and update data/all_stats.json."""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

JST = timezone(timedelta(hours=9))
BASE_URL = "https://note.com/api/v1"
DATA_FILE = Path(__file__).parent.parent / "data" / "all_stats.json"


def fetch_all_stats(session_cookie: str) -> list[dict]:
    headers = {
        "Cookie": f"_note_session={session_cookie}",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://note.com/",
    }

    all_stats = []
    page = 1

    while True:
        resp = requests.get(
            f"{BASE_URL}/stats/pv",
            params={"filter": "all", "page": page, "sort": "pv"},
            headers=headers,
            timeout=30,
        )

        if resp.status_code == 401:
            print("ERROR: Session expired. Update NOTE_SESSION_COOKIE secret.", file=sys.stderr)
            sys.exit(1)

        resp.raise_for_status()
        data = resp.json().get("data", {})
        stats = data.get("stats", [])

        if not stats:
            break

        all_stats.extend(stats)

        if data.get("is_last_page", True) or len(stats) < 20:
            break

        page += 1

    return all_stats


def update_all_stats(today: str, fetched: list[dict]) -> None:
    if DATA_FILE.exists():
        with open(DATA_FILE, encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {"last_updated": "", "dates": [], "articles": []}

    dates = db["dates"]

    if today in dates:
        date_idx = dates.index(today)
        print(f"Overwriting existing data for {today}.")
    else:
        dates.append(today)
        date_idx = len(dates) - 1

    articles_by_key: dict[str, dict] = {a["key"]: a for a in db["articles"]}

    for stat in fetched:
        key = stat["key"]
        if key not in articles_by_key:
            articles_by_key[key] = {
                "key": key,
                "name": stat.get("name", ""),
                "published_at": stat.get("publish_at", ""),
                "total_pv": 0,
                "like_count": 0,
                "pv_history": [None] * len(dates),
            }

        article = articles_by_key[key]
        article["name"] = stat.get("name", article["name"])
        article["total_pv"] = stat.get("pv", 0)
        article["like_count"] = stat.get("like_count", 0)

        while len(article["pv_history"]) < len(dates):
            article["pv_history"].append(None)

        article["pv_history"][date_idx] = stat.get("pv", 0)

    db["last_updated"] = today
    db["dates"] = dates
    db["articles"] = sorted(
        articles_by_key.values(),
        key=lambda a: a["total_pv"],
        reverse=True,
    )

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    print(f"Saved: {len(db['articles'])} articles, {len(dates)} days of data.")


def main() -> None:
    session_cookie = os.environ.get("NOTE_SESSION_COOKIE", "").strip()
    if not session_cookie:
        print("ERROR: NOTE_SESSION_COOKIE environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    today = datetime.now(JST).strftime("%Y-%m-%d")
    print(f"Collecting stats for {today} ...")

    fetched = fetch_all_stats(session_cookie)
    print(f"Fetched {len(fetched)} articles from note.com API.")

    update_all_stats(today, fetched)


if __name__ == "__main__":
    main()
