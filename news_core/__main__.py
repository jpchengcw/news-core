"""CLI: `python -m news_core fetch <ticker> [...]`.

Loads .env from the current directory if present. Useful for ad-hoc
verification that locale inference, source tiering, and translation
are wired correctly against a real query.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path


def _load_env(path: Path) -> None:
    """Tiny dotenv loader. We don't want python-dotenv as a hard dep."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="news_core", description="multilingual news fetch")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fetch", help="fetch ranked news for a ticker")
    p.add_argument("ticker")
    p.add_argument("--name", required=True, help="company name (fallback for query construction)")
    p.add_argument("--geo", action="append", default=[], help="business_geography tag (repeatable)")
    p.add_argument("--lookback", type=int, default=72, help="hours")
    p.add_argument("--max", type=int, default=20, help="max items")
    p.add_argument("--min-tier", type=int, default=2, help="0=S, 1, 2, 3")
    p.add_argument("--consumer", default="deep_dive", choices=["pm_pulse", "deep_dive"])
    p.add_argument("--cache-dir", default=".cache/news_core")
    p.add_argument("--region", default=None)
    p.add_argument("--env", default=".env", help="path to .env file (best-effort)")
    p.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    _load_env(Path(args.env))

    # Import after env load so backends pick up keys.
    from news_core import NewsClient

    client = NewsClient(cache_dir=args.cache_dir, consumer=args.consumer)
    result = client.fetch(
        ticker=args.ticker,
        company_name=args.name,
        business_geography=args.geo,
        lookback_hours=args.lookback,
        max_items=args.max,
        min_tier=args.min_tier,
        region=args.region,
    )

    print(f"locales:        {', '.join(result.locales_queried)}")
    print(f"queries issued: {result.queries_issued}")
    print(f"raw hits:       {result.raw_hits}")
    print(f"clusters:       {result.deduped_clusters}")
    print(f"dropped tier:   {result.dropped_below_tier}")
    print(f"items:          {len(result.items)}")
    print()
    for i, it in enumerate(result.items, 1):
        score = f"{it.score:.2f}"
        title = it.title_translated or it.title_original
        print(f"{i:>2}. [{it.tier.name:>4}] [{it.locale}] {it.source_name}  ·  score {score}")
        print(f"    {title}")
        if it.title_translated and it.title_translated != it.title_original:
            print(f"    orig: {it.title_original}")
        if it.analyst_gloss:
            print(f"    {it.analyst_gloss}")
        print(f"    {it.url}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
