import json
import re
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
import os

import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from stocks.models import IncomeStatement, Stock
from AlgoAnywhere.settings import BASE_DIR


# SEC EDGAR API endpoints
SEC_COMPANYFACTS_BULK = (
    "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
)
SEC_TICKER_CIK = (
    "https://www.sec.gov/include/ticker.txt"
)
SEC_COMPANYFACTS_API = "https://data.sec.gov/api/xbrl/companyfacts/CIK{}.json"
SEC_HEADERS = {
    "User-Agent": "AlgoAnywhere Research Tool contact@example.com",
    "Accept": "application/json",
}

# US-GAAP concept mappings to IncomeStatement fields
CONCEPT_MAP = {
    "Revenues": "revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "SalesRevenueNet": "revenue",
    "CostOfGoodsAndServicesSold": "cost_of_revenue",
    "CostOfRevenue": "cost_of_revenue",
    "GrossProfit": "gross_profit",
    "OperatingExpenses": "operating_expenses",
    "ResearchAndDevelopmentExpense": "research_and_development",
    "SellingGeneralAndAdministrativeExpense": "selling_general_and_administrative",
    "OperatingIncomeLoss": "operating_income",
    "InterestExpense": "interest_expense",
    "InterestIncome": "interest_income",
    "OtherIncomeExpense": "other_income_expense",
    "IncomeBeforeEquityMethodInvestments": "income_before_tax",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": "income_before_tax",
    "IncomeTaxExpenseBenefit": "income_tax_expense",
    "NetIncomeLoss": "net_income",
    "EarningsPerShareBasic": "earnings_per_share_basic",
    "EarningsPerShareDiluted": "earnings_per_share_diluted",
}


def _get_cik_from_ticker(ticker, submissions_data):
    """Find CIK for a ticker from submissions data."""
    for cik, data in submissions_data.items():
        if isinstance(data, dict):
            tickers = data.get("tickers", [])
            if ticker.upper() in [t.upper() for t in tickers]:
                return cik.zfill(10)
    return None


def _parse_period(fact):
    """Extract fiscal year, quarter, and end date from XBRL fact."""
    end = fact.get("end")
    if not end:
        return None, None, None

    try:
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        return None, None, None

    fiscal_year = end_date.year
    fiscal_quarter = None

    # Check if it's a quarterly period (duration ~91 days)
    start = fact.get("start")
    if start:
        try:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
            days = (end_date - start_date).days
            if 60 <= days <= 120:  # Quarterly
                month = end_date.month
                if month in (3, 4, 5):
                    fiscal_quarter = 1
                elif month in (6, 7, 8):
                    fiscal_quarter = 2
                elif month in (9, 10, 11):
                    fiscal_quarter = 3
                else:
                    fiscal_quarter = 4
        except ValueError:
            pass

    return fiscal_year, fiscal_quarter, end_date


def _extract_income_statement_data(company_facts_json):
    """Extract income statement data from SEC company facts JSON."""
    facts = company_facts_json.get("facts", {})
    us_gaap = facts.get("us-gaap", {})
    if not us_gaap:
        return []

    period_data = {}

    for concept_name, concept_data in us_gaap.items():
        field_name = CONCEPT_MAP.get(concept_name)
        if not field_name:
            continue

        units = concept_data.get("units", {})
        for unit_key, unit_facts in units.items():
            # Only process USD amounts or shares (for EPS)
            if "USD" not in unit_key and "shares" not in unit_key.lower():
                continue

            for fact in unit_facts:
                fiscal_year, fiscal_quarter, end_date = _parse_period(fact)
                if not end_date:
                    continue

                key = (end_date, fiscal_year, fiscal_quarter)
                if key not in period_data:
                    period_data[key] = {
                        "period_end_date": end_date,
                        "fiscal_year": fiscal_year,
                        "fiscal_quarter": fiscal_quarter,
                        "form_type": fact.get("form"),
                        "filing_date": fact.get("filed"),
                    }

                val = fact.get("val")
                if val is None:
                    continue

                # Use the most recent filing for each period (if multiple)
                existing_val = period_data[key].get(field_name)
                if existing_val is None:
                    if field_name in ("earnings_per_share_basic", "earnings_per_share_diluted"):
                        period_data[key][field_name] = float(val)
                    else:
                        period_data[key][field_name] = int(val)

    return list(period_data.values())


class Command(BaseCommand):
    help = (
        "Download SEC EDGAR income statement data. "
        "Use --bulk to download bulk ZIP, or --ticker=TICKER for a specific stock."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--bulk",
            action="store_true",
            help="Download bulk companyfacts.zip and process all companies",
        )
        parser.add_argument(
            "--from_local",
            action="store_true",
            help="Use loacl companyfacts.zip and ticker_cik.txt file",
        )
        parser.add_argument(
            "--ticker",
            type=str,
            help="Process a specific ticker (requires stock to exist in database)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit number of companies to process (for testing)",
        )

    def handle(self, *args, **options):
        if options["bulk"]:
            self._process_bulk(limit=options.get("limit"), from_local=options.get("from_local"))
        elif options["ticker"]:
            self._process_ticker(options["ticker"])
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Specify --bulk to download bulk data or --ticker=TICKER for a specific stock."
                )
            )

    def _process_bulk(self, limit=None, from_local=False):
        if not from_local:
            self.stdout.write("Downloading SEC EDGAR bulk companyfacts.zip...")
            try:
                resp = requests.get(SEC_COMPANYFACTS_BULK, headers=SEC_HEADERS, timeout=300)
                resp_ticker_cik = requests.get(SEC_TICKER_CIK, headers=SEC_HEADERS, timeout=300)
                resp.raise_for_status()
                resp_ticker_cik.raise_for_status()
            except requests.RequestException as e:
                self.stderr.write(self.style.ERROR(f"Failed to download bulk ZIP: {e}"))
                return
            
            self.stdout.write(f"  Downloaded {len(resp.content) / 1024 / 1024:.1f} MB")
            companyfacts_data = resp.content
            cik_ticker_data = resp_ticker_cik.text
        else:
            current_folder = os.path.join(BASE_DIR, 'stocks', 'management', 'commands')
            with open(os.path.join(current_folder, 'companyfacts.zip'), 'rb') as f:
                companyfacts_data = f.read()
            with open(os.path.join(current_folder, 'ticker.txt'), 'r') as f:
                cik_ticker_data = f.read()

        # Build ticker lookup from database
        stocks_dict = {s.ticker.upper(): s for s in Stock.objects.all()}
        self.stdout.write(f"  Processing {len(stocks_dict)} stocks from database...")

        # Extract and process ZIP
        try:
            lines = cik_ticker_data.splitlines()
            cik_ticker_mapper = {
                line.split('\t')[1].strip().zfill(7): line.split('\t')[0].strip()
                for line in lines if '\t' in line
            }

            with zipfile.ZipFile(BytesIO(companyfacts_data)) as z:
                files = [f for f in z.namelist() if f.endswith(".json")]
                self.stdout.write(f"  Found {len(files)} company fact files in ZIP")

                processed = 0
                created = 0
                updated = 0
                failed = 0
                skipped_no_match = 0

                for filename in files[: (limit or len(files))]:
                    try:
                        with z.open(filename) as f:
                            data = json.load(f)
                            cik = str(data.get("cik")).zfill(7)
                            if not cik:
                                continue

                            # Find matching stock by cik
                            tickers = cik_ticker_mapper.get(cik)
                            if not tickers:
                                skipped_no_match += 1
                                continue
                            tickers = tickers.upper()

                            stock = None
                            for ticker in tickers:
                                stock = stocks_dict.get(ticker.upper())
                                if stock:
                                    break

                            if not stock:
                                skipped_no_match += 1
                                continue

                            statements = _extract_income_statement_data(data)
                            if not statements:
                                continue

                            # Save income statements
                            for stmt_data in statements:
                                try:
                                    filing_date_str = stmt_data.get("filing_date")
                                    filing_date = None
                                    if filing_date_str:
                                        try:
                                            filing_date = datetime.strptime(
                                                filing_date_str, "%Y-%m-%d"
                                            ).date()
                                        except (ValueError, TypeError):
                                            pass

                                    obj, was_created = IncomeStatement.objects.update_or_create(
                                        stock=stock,
                                        period_end_date=stmt_data["period_end_date"],
                                        fiscal_year=stmt_data["fiscal_year"],
                                        fiscal_quarter=stmt_data.get("fiscal_quarter"),
                                        defaults={
                                            "form_type": stmt_data.get("form_type"),
                                            "filing_date": filing_date,
                                            "revenue": stmt_data.get("revenue"),
                                            "cost_of_revenue": stmt_data.get("cost_of_revenue"),
                                            "gross_profit": stmt_data.get("gross_profit"),
                                            "operating_expenses": stmt_data.get(
                                                "operating_expenses"
                                            ),
                                            "research_and_development": stmt_data.get(
                                                "research_and_development"
                                            ),
                                            "selling_general_and_administrative": stmt_data.get(
                                                "selling_general_and_administrative"
                                            ),
                                            "operating_income": stmt_data.get("operating_income"),
                                            "interest_expense": stmt_data.get("interest_expense"),
                                            "interest_income": stmt_data.get("interest_income"),
                                            "other_income_expense": stmt_data.get(
                                                "other_income_expense"
                                            ),
                                            "income_before_tax": stmt_data.get(
                                                "income_before_tax"
                                            ),
                                            "income_tax_expense": stmt_data.get(
                                                "income_tax_expense"
                                            ),
                                            "net_income": stmt_data.get("net_income"),
                                            "earnings_per_share_basic": stmt_data.get(
                                                "earnings_per_share_basic"
                                            ),
                                            "earnings_per_share_diluted": stmt_data.get(
                                                "earnings_per_share_diluted"
                                            ),
                                        },
                                    )
                                    if was_created:
                                        created += 1
                                    else:
                                        updated += 1
                                except Exception as e:
                                    failed += 1
                                    if failed <= 10:
                                        self.stdout.write(
                                            self.style.WARNING(
                                                f"  Skip {stock.ticker} {stmt_data.get('period_end_date')}: {e}"
                                            )
                                        )

                            processed += 1
                            if processed % 100 == 0:
                                self.stdout.write(
                                    f"  Processed {processed} companies ({created} created, {updated} updated)..."
                                )

                    except Exception as e:
                        failed += 1
                        if failed <= 10:
                            self.stdout.write(
                                self.style.WARNING(f"  Error processing {filename}: {e}")
                            )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Income statements: {processed} companies processed, "
                        f"{created} created, {updated} updated, {failed} failed, "
                        f"{skipped_no_match} skipped (no matching ticker)."
                    )
                )

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error processing ZIP: {e}"))

    def _process_ticker(self, ticker, from_local=False):
        stock = Stock.objects.filter(ticker=ticker.upper()).first()
        if not stock:
            self.stderr.write(
                self.style.ERROR(f"Stock with ticker '{ticker}' not found in database.")
            )
            return

        # Find CIK - we'd need submissions data or a mapping
        # For now, try common CIK lookup patterns
        self.stdout.write(f"Fetching SEC data for {ticker}...")
        self.stdout.write(
            self.style.WARNING(
                "Note: CIK lookup not implemented. Use --bulk for full processing."
            )
        )
