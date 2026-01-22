import re

import requests
from django.core.management.base import BaseCommand

from stocks.models import Stock

# NASDAQ screener: https://www.nasdaq.com/market-activity/stocks/screener
# API has no country param. We only request US exchanges (NASDAQ, NYSE, AMEX) to avoid
# downloading international exchanges (LSE, TSX, etc.), then filter country=United States.
NASDAQ_API = "https://api.nasdaq.com/api/screener/stocks"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}
PAGE_SIZE = 1000
US_EXCHANGES = ("NASDAQ", "NYSE", "AMEX")
US_COUNTRIES = frozenset({"united states", "usa", "us"})


def _parse_market_cap(raw) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw) if raw == raw else None  # NaN check
    s = str(raw).strip()
    if not s or s.lower() in ("—", "-", "n/a", "nan", ""):
        return None
    s = re.sub(r"[,~\s]", "", s)
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        pass
    m = re.match(r"^\$?([\d.]+)\s*([KMBT])?$", s, re.I)
    if not m:
        return None
    num = float(m.group(1))
    suffix = (m.group(2) or "").upper()
    mult = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
    return int(num * mult.get(suffix, 1))


def _get(r, *keys, default=None):
    for k in keys:
        if isinstance(r, dict) and k in r:
            v = r[k]
            if v is not None and str(v).strip().lower() not in ("", "n/a", "—", "nan"):
                return v
    return default


def _get_market_cap(row):
    return (
        row.get("marketCap")
        or row.get("market_cap")
        or row.get("marketcap")
        or row.get("Market Cap")
    )


class Command(BaseCommand):
    help = (
        "Update database: use --update_stock_list to fetch from NASDAQ screener "
        "(Country=United States) and upsert the stock list."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--update_stock_list",
            action="store_true",
            help="Fetch NASDAQ screener (United States), download and update stock list.",
        )

    def handle(self, *args, **options):
        if options["update_stock_list"]:
            self._update_stock_list()
        else:
            self.stdout.write(
                self.style.WARNING("Specify --update_stock_list to update the stock list.")
            )

    def _update_stock_list(self):
        self.stdout.write(
            "Fetching from NASDAQ screener (US exchanges only: NASDAQ, NYSE, AMEX)..."
        )

        all_rows = []
        for exchange in US_EXCHANGES:
            offset = 0
            while True:
                try:
                    resp = requests.get(
                        NASDAQ_API,
                        headers=HEADERS,
                        params={
                            "tableonly": "true",
                            "limit": PAGE_SIZE,
                            "offset": offset,
                            "download": "true",
                            "exchange": exchange,
                        },
                        timeout=30,
                    )
                    resp.raise_for_status()
                    j = resp.json()
                except requests.RequestException as e:
                    self.stderr.write(
                        self.style.ERROR(f"NASDAQ API request failed ({exchange}): {e}")
                    )
                    return
                except ValueError as e:
                    self.stderr.write(
                        self.style.ERROR(f"NASDAQ API invalid JSON ({exchange}): {e}")
                    )
                    return

                data = j.get("data") or {}
                tbl = data.get("table") or {}
                rows = tbl.get("rows") or data.get("rows") or []

                if not rows:
                    break

                all_rows.extend(rows)
                self.stdout.write(f"  {exchange}: +{len(rows)} → total {len(all_rows)}")

                # API often ignores limit/offset and returns the full exchange in one go.
                # If we got more than we asked for, or a partial page, we're done.
                if len(rows) < PAGE_SIZE or len(rows) > PAGE_SIZE:
                    break
                offset += PAGE_SIZE

        self.stdout.write(f"  Total fetched: {len(all_rows)} (US exchanges only)")

        # Filter: Country = United States (exclude non-US listed on NASDAQ/NYSE/AMEX)
        us = [
            row
            for row in all_rows
            if (str(_get(row, "country", "Country", "countryname") or "")).strip().lower()
            in US_COUNTRIES
        ]
        self.stdout.write(f"  Filtered to {len(us)} United States stocks.")

        created = 0
        updated = 0
        failed = 0

        for i, row in enumerate(us):
            ticker = (str(_get(row, "symbol", "Symbol", "ticker") or "")).strip()
            if not ticker:
                continue

            name = _get(row, "name", "Name", "company", "security") or ticker
            sector = _get(row, "sector", "Sector", "industry", "Industry") or ""
            market_cap = _parse_market_cap(_get_market_cap(row))

            name_val = str(name).strip()[:255] if name else ticker
            sector_val = (str(sector).strip()[:100] or None) if sector else None

            try:
                _, was_created = Stock.objects.update_or_create(
                    ticker=ticker,
                    defaults={
                        "name": name_val,
                        "sector": sector_val,
                        "market_cap": market_cap,
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                failed += 1
                self.stdout.write(self.style.WARNING(f"  Skip {ticker}: {e}"))

            if (i + 1) % 500 == 0:
                self.stdout.write(f"  Processed {i + 1} / {len(us)}...")

        self.stdout.write(
            self.style.SUCCESS(
                f"Stock list updated: {created} created, {updated} updated, {failed} failed."
            )
        )
