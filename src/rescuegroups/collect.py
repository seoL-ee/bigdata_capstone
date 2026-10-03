"""Collect available animals from the RescueGroups.org API v5."""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv


BASE_URL = "https://api.rescuegroups.org/v5"
PAGE_SIZE = 250
ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "rescuegroups" / "raw"


def fetch_page(session, species, page, limit, retries=3):
    url = f"{BASE_URL}/public/animals/search/available/{species.lower()}/"
    for attempt in range(retries + 1):
        try:
            response = session.get(
                url,
                params={"page": page, "limit": limit},
                timeout=30,
            )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < retries:
                    time.sleep(min(2**attempt, 30))
                    continue
            response.raise_for_status()
            return response.json(), attempt
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(min(2**attempt, 30))


def fetch_animals(species, count=None, collect_all=False, request_delay=0.5):
    api_key = os.getenv("RESCUEGROUPS_API_KEY")
    if not api_key:
        raise RuntimeError("RESCUEGROUPS_API_KEY is not set")

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": api_key,
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json",
        }
    )

    animals = []
    included = []
    seen_ids = set()
    duplicate_count = 0
    raw_count = 0
    retry_count = 0
    reported_count = None
    page = 1
    request_page_size = PAGE_SIZE if collect_all else min(PAGE_SIZE, count)

    while collect_all or len(animals) < count:
        payload, page_retries = fetch_page(
            session,
            species,
            page,
            request_page_size,
        )
        retry_count += page_retries
        rows = payload.get("data") or []
        if not rows:
            break
        raw_count += len(rows)

        meta = payload.get("meta", {})
        if reported_count is None:
            reported_count = meta.get("count")

        for animal in rows:
            animal_id = animal.get("id")
            if animal_id in seen_ids:
                duplicate_count += 1
                continue
            seen_ids.add(animal_id)
            animals.append(animal)
            if not collect_all and len(animals) == count:
                break

        included.extend(payload.get("included") or [])
        print(f"species={species} page={page} collected={len(animals)}")

        if not collect_all and len(animals) >= count:
            break
        pages = meta.get("pages")
        if pages is not None and page >= int(pages):
            break
        page += 1
        time.sleep(request_delay)

    return animals, included, raw_count, duplicate_count, reported_count, retry_count


def save_json(path, metadata, animals, included):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": metadata,
        "data": animals,
        "included": included,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--species", choices=["dogs", "cats"], required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--count", type=int)
    mode.add_argument("--all", action="store_true", dest="collect_all")
    args = parser.parse_args()

    if args.count is None and not args.collect_all:
        args.count = 1000
    if args.count is not None and args.count < 1:
        parser.error("--count must be at least 1")

    load_dotenv(ROOT / ".env")
    started = datetime.now(timezone.utc)
    if args.collect_all:
        timestamp = started.strftime("%Y%m%dT%H%M%SZ")
        output = RAW_DIR / f"{args.species}_available_all_{timestamp}.json"
    else:
        output = RAW_DIR / f"{args.species}_available.json"

    try:
        animals, included, raw_count, duplicates, reported_count, retries = fetch_animals(
            args.species,
            args.count,
            args.collect_all,
        )
        finished = datetime.now(timezone.utc)
        metadata = {
            "species": args.species,
            "collection_time": finished.isoformat(),
            "collected_count": len(animals),
            "raw_count": raw_count,
            "unique_count": len(animals),
            "duplicate_count": duplicates,
            "collection_mode": "all" if args.collect_all else "count",
            "requested_count": None if args.collect_all else args.count,
            "reported_available_count": reported_count,
            "reported_count_difference": (
                len(animals) - reported_count if reported_count is not None else None
            ),
            "retry_count": retries,
            "elapsed_seconds": round((finished - started).total_seconds(), 3),
            "api_base_url": BASE_URL,
            "source_endpoint": (
                f"{BASE_URL}/public/animals/search/available/{args.species}/"
            ),
            "failed": False,
        }
        save_json(output, metadata, animals, included)
    except (requests.RequestException, RuntimeError, ValueError) as error:
        print(f"collection failed: {error}")
        return 1

    print(
        f"species={args.species} collected={len(animals)} "
        f"duplicates={duplicates} reported={reported_count} retries={retries} "
        f"failed=false elapsed_seconds={metadata['elapsed_seconds']} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
