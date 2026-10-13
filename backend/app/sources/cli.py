"""Manual scraping:  python -m app.sources.cli [--trades delivery driver] [--pages 1]     |     --stats"""
import argparse
import json
import sys

from .. import db
from .apna import TRADE_SLUGS, Fetcher, ScrapeError, scrape_trade


def print_stats() -> None:
    with db.connect() as con:
        print("cached listings:", con.execute("SELECT COUNT(*) FROM listings").fetchone()[0])
        for r in con.execute("SELECT trades, COUNT(*) n, MAX(acquired_at) last FROM listings GROUP BY trades ORDER BY n DESC"):
            print(f"  {r['trades']:<28} {r['n']:>4}   last fetched {r['last']}")
        for r in con.execute("SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 8"):
            print(f"  run {r['id']:>3} {r['trade']:<16} {r['status']:<6} {r['error_message'] or ''}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trades", nargs="*", default=list(TRADE_SLUGS))
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    if a.stats:
        print_stats()
        return 0
    try:
        fetcher = Fetcher()
    except ScrapeError as e:
        print(f"Cannot start scraper: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    results = [scrape_trade(fetcher, t, a.pages) for t in a.trades]
    print(json.dumps(results, indent=2))
    return 0 if all(r["status"] == "ok" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
