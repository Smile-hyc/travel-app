"""Run the content ingestion pipeline without exposing the admin HTTP API.

Examples:
    python scripts/sync_content.py --official-source dpm
    python scripts/sync_content.py --limit 10 --include-official
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main_state import (
    amap_client,
    content_ingestion_service,
    mediacrawler_import_service,
    review_store,
    tikhub_review_client,
)


async def _run(args: argparse.Namespace) -> None:
    await amap_client.startup()
    try:
        if args.import_mediacrawler:
            if not args.city:
                raise SystemExit("--import-mediacrawler 必须同时提供 --city")
            result = await mediacrawler_import_service.import_export(
                file_name=args.import_mediacrawler,
                city_name=args.city,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.bootstrap_city:
            result = await content_ingestion_service.bootstrap_city(
                city_name=args.bootstrap_city,
                limit=args.limit,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.official_source:
            source_ids = (
                ("dpm", "jiuzhai", "huangshan", "bmy", "panda")
                if args.official_source == "all"
                else (args.official_source,)
            )
            results = [
                (await content_ingestion_service.sync_official(source_id)).model_dump()
                for source_id in source_ids
            ]
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            run = await content_ingestion_service.start_run(
                limit=args.limit,
                force_refresh=args.force,
                include_official=args.include_official,
            )
            task = content_ingestion_service._tasks[run["run_id"]]
            await task
            final = content_ingestion_service.get_run(run["run_id"])
            print(json.dumps(final, ensure_ascii=False, indent=2))
        print(json.dumps(review_store.get_content_stats(), ensure_ascii=False, indent=2))
    finally:
        await tikhub_review_client.aclose()
        await amap_client.shutdown()
        review_store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="同步热门 POI 的 UGC 和景区官方信息")
    parser.add_argument("--limit", type=int, default=10, choices=range(1, 31))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--include-official", action="store_true")
    parser.add_argument(
        "--official-source",
        choices=("all", "dpm", "jiuzhai", "huangshan", "bmy", "panda"),
    )
    parser.add_argument("--bootstrap-city")
    parser.add_argument("--import-mediacrawler")
    parser.add_argument("--city")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
