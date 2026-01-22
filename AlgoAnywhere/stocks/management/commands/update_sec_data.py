"""
Django management command to download and process SEC EDGAR income statement data.

This command downloads SEC company facts data from the EDGAR database and
extracts quarterly and annual income statement information for stocks
in the database.

Usage:
    python manage.py update_sec_data --bulk [--from_local] [--limit=N]

Options:
    --bulk: Download bulk companyfacts.zip and process all companies
    --from_local: Use local files instead of downloading
    --limit: Limit number of companies to process (for testing)
"""

import json
import zipfile
from datetime import datetime
from io import BytesIO
import os
import pandas as pd
import time
from functools import wraps

import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from stocks.models import IncomeStatement, Stock
from AlgoAnywhere.settings import BASE_DIR


def timing_decorator(func):
    """
    Decorator to measure and report execution time with progress prediction and live progress bar.
    
    Provides timing information, estimates completion time based on current progress,
    and displays a live progress bar showing completion percentage.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        start_time = time.time()
        self.stdout.write(f"⏱️  Starting {func.__name__} at {datetime.now().strftime('%H:%M:%S')}")
        
        # Get total items for progress tracking
        total_items = kwargs.get('limit') or getattr(self, '_total_items', 0)
        if total_items > 0:
            self.stdout.write(f"📊  Processing {total_items:,} total items")
        
        result = func(self, *args, **kwargs)
        
        end_time = time.time()
        total_time = end_time - start_time
        final_processed = getattr(self, '_processed_count', 0)
        
        # Calculate timing metrics
        if final_processed > 0:
            avg_time_per_item = total_time / final_processed
            self.stdout.write(f"⏱️  Completed {func.__name__} in {total_time:.1f}s")
            self.stdout.write(f"📊  Average time per company: {avg_time_per_item:.2f}s")
        
        return result
    
    return wrapper



# SEC EDGAR API endpoints
SEC_COMPANYFACTS_BULK = (
    "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
)
SEC_TICKER_CIK = (
    "https://www.sec.gov/files/company_tickers.json"
)
SEC_HEADERS = {
    "User-Agent": "AlgoAnywhere Research Tool contact@example.com",
    "Accept": "application/json",
}

# US-GAAP concept mappings to IncomeStatement model fields
# Maps SEC XBRL concepts to our database field names
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


def _parse_period(fact):
    """
    Extract fiscal year, quarter, and end date from SEC XBRL fact.
    
    Args:
        fact (dict): SEC XBRL fact containing period information
        
    Returns:
        tuple: (fiscal_year, fiscal_quarter, end_date) or (None, None, None) if invalid
        
    Note:
        - Fiscal year is derived from the period end date
        - Fiscal quarter is determined by the period duration and end month
        - Quarterly periods are typically 60-120 days
    """
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
    """
    Extract income statement data from SEC company facts JSON.
    
    This function processes SEC company facts data and extracts quarterly/annual
    income statement information, grouping by fiscal period and selecting the most
    recent filing data for each period.
    
    Args:
        company_facts_json (dict): SEC company facts JSON data
        
    Returns:
        list: List of dictionaries containing income statement data for each fiscal period
        
    Processing Logic:
        1. Maps US-GAAP concepts to database fields using CONCEPT_MAP
        2. Groups data by fiscal year, quarter, and form type to prevent duplicates
        3. For each fiscal period, uses the most recent filing data
        4. Filters out future dates and incomplete records
        5. Only includes records with meaningful financial data (revenue or net income)
    """
    facts = company_facts_json.get("facts", {})
    us_gaap = facts.get("us-gaap", {})
    if not us_gaap:
        return []

    # Group by fiscal year, quarter, and form type to prevent duplicates
    # This ensures we only get one record per fiscal period per company
    period_data = {}

    for concept_name, concept_data in us_gaap.items():
        field_name = CONCEPT_MAP.get(concept_name)
        if not field_name:
            continue

        units = concept_data.get("units", {})
        for unit_key, unit_facts in units.items():
            # Only process USD amounts or shares (for EPS)
            # Skip other units like shares, USD/shares, etc.
            if "USD" not in unit_key and "shares" not in unit_key.lower():
                continue

            for fact in unit_facts:
                fiscal_year, fiscal_quarter, end_date = _parse_period(fact)
                # Filter out future dates and invalid periods
                if not end_date or fiscal_year > datetime.now().year + 1:
                    continue

                # Create a unique key for fiscal year, quarter, and form type
                # This ensures we only get one record per fiscal period
                key = (fiscal_year, fiscal_quarter, fact.get("form", ""))
                
                if key not in period_data:
                    period_data[key] = {
                        "period_end_date": end_date,
                        "fiscal_year": fiscal_year,
                        "fiscal_quarter": fiscal_quarter,
                        "form_type": fact.get("form"),
                        "filing_date": fact.get("filed"),
                    }

                val = fact.get("val")
                # Skip None and zero values to maintain data quality
                # Zero values often indicate missing or placeholder data
                if val is not None and val != 0:
                    # Use most recent filing data for each fiscal period
                    # This ensures we have the latest and most accurate information
                    existing_val = period_data[key].get(field_name)
                    existing_filing_date = period_data[key].get("filing_date")
                    current_filing_date = fact.get("filed")
                    
                    # Use the most recent filing data
                    if (existing_val is None or 
                        (current_filing_date and existing_filing_date and current_filing_date > existing_filing_date)):
                        
                        # Handle EPS values as floats, everything else as integers
                        # EPS values can have decimal places, other values are typically whole numbers
                        if field_name in ("earnings_per_share_basic", "earnings_per_share_diluted"):
                            period_data[key][field_name] = float(val)
                        else:
                            period_data[key][field_name] = int(val)
                        
                        # Update filing date and period end date if more recent
                        # This ensures we track the most current filing information
                        if current_filing_date:
                            period_data[key]["filing_date"] = current_filing_date
                        # Keep the most recent period end date for this fiscal period
                        # Some companies may file amendments with different end dates
                        if end_date > period_data[key]["period_end_date"]:
                            period_data[key]["period_end_date"] = end_date

    # Convert to list and filter out incomplete records
    # Only include records that have meaningful financial data
    result = []
    for data in period_data.values():
        # Only include records that have at least revenue or net income
        # This filters out records with only minor line items
        if data.get("revenue") or data.get("net_income"):
            result.append(data)
    
    return result


class Command(BaseCommand):
    """
    Django management command for updating SEC EDGAR income statement data.
    
    This command downloads SEC company facts data and processes it to populate
    the IncomeStatement model with quarterly and annual financial data.
    """
    help = "Download SEC EDGAR income statement data. Use --bulk to download bulk ZIP."

    def add_arguments(self, parser):
        """
        Define command line arguments for the management command.
        
        Args:
            parser (ArgumentParser): Django argument parser
        """
        parser.add_argument(
            "--bulk",
            action="store_true",
            help="Download bulk companyfacts.zip and process all companies",
        )
        parser.add_argument(
            "--from_local",
            action="store_true",
            help="Use local companyfacts.zip and company_tickers.json file",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit number of companies to process (for testing)",
        )

    def handle(self, *args, **options):
        """
        Main entry point for the management command.
        
        Args:
            *args: Additional positional arguments
            **options: Command line options
        """
        if options["bulk"]:
            self._process_bulk(limit=options.get("limit"), from_local=options.get("from_local"))
        else:
            self.stdout.write(
                self.style.WARNING("Specify --bulk to download bulk data.")
            )

    @timing_decorator
    def _process_bulk(self, limit=None, from_local=False):
        """
        Process SEC company facts data in bulk.
        
        Downloads or loads local SEC data, extracts income statement information,
        and updates the database with the processed data.
        
        Args:
            limit (int, optional): Maximum number of companies to process
            from_local (bool): Whether to use local files instead of downloading
        """
        start_time = time.time()  # Track start time for live predictions
        if not from_local:
            # Download bulk data from sec.gov
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
            cik_ticker_mapper = resp_ticker_cik.text
        else:
            # Use local files for development/testing
            try:
                self.stdout.write(f"  Reading local companyfacts.zip...")
                current_folder = os.path.join(BASE_DIR, 'stocks', 'management', 'commands')
                with open(os.path.join(current_folder, 'companyfacts.zip'), 'rb') as f:
                    companyfacts_data = f.read()
                self.stdout.write(f"  Reading local company_tickers.json...")
                cik_ticker_mapper = pd.read_json(os.path.join(current_folder, 'company_tickers.json')).T
                cik_ticker_mapper = cik_ticker_mapper.set_index('cik_str')['ticker'].to_dict()

            except FileNotFoundError as e:
                self.stderr.write(self.style.ERROR(f"Failed to find local files: {e}"))
                return

        # Build ticker lookup from database for efficient matching
        stocks_dict = {s.ticker.upper(): s for s in Stock.objects.all()}
        self.stdout.write(f"  Processing {len(stocks_dict)} stocks from database...")
        
        # Set total items for timing predictions
        self._total_items = limit or 19140  # Total files in ZIP

        # Extract and process ZIP file containing company facts
        try:
            with zipfile.ZipFile(BytesIO(companyfacts_data)) as z:
                files = [f for f in z.namelist() if f.endswith(".json")]
                self.stdout.write(f"  Found {len(files)} company fact files in ZIP")
                
                # Initialize counters for progress tracking
                processed = 0
                files_processed = 0  # Track actual file progress
                created = 0
                updated = 0
                failed = 0
                skipped_no_match = 0
                batch_size = 50  # Process companies in batches for memory efficiency
                
                # Process files in batches with transaction management
                # This prevents memory issues and ensures data consistency
                for batch_start in range(0, len(files[: (limit or len(files))]), batch_size):
                    batch_end = min(batch_start + batch_size, limit or len(files))
                    batch_files = files[batch_start:batch_end]
                    
                    # Use atomic transactions for data consistency
                    with transaction.atomic():
                        # Process each company file in the current batch
                        for filename in batch_files:
                            files_processed += 1  # Track actual file progress - increment for EVERY file
                            
                            try:
                                with z.open(filename) as f:
                                    data = json.load(f)
                                    cik = data.get("cik")
                                    if not cik:
                                        continue

                                    # CIK is already an integer, use it directly
                                    ticker = cik_ticker_mapper.get(cik)
                                    if not ticker:
                                        skipped_no_match += 1
                                        continue

                                    # Find matching stock in database
                                    stock = stocks_dict.get(ticker.upper())
                                    if not stock:
                                        skipped_no_match += 1
                                        continue

                                    # Extract income statement data from SEC facts
                                    statements = _extract_income_statement_data(data)
                                    if not statements:
                                        continue

                                    # Save income statements using individual creates to avoid conflicts
                                    created_count = 0
                                    for stmt_data in statements:
                                        try:
                                            # Parse filing date for database storage
                                            filing_date_str = stmt_data.get("filing_date")
                                            filing_date = None
                                            if filing_date_str:
                                                try:
                                                    filing_date = datetime.strptime(
                                                        filing_date_str, "%Y-%m-%d"
                                                    ).date()
                                                except (ValueError, TypeError):
                                                    pass

                                            # Use get_or_create to handle unique constraints
                                            # This prevents duplicate records for the same fiscal period
                                            obj, was_created = IncomeStatement.objects.get_or_create(
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
                                                    "operating_expenses": stmt_data.get("operating_expenses"),
                                                    "research_and_development": stmt_data.get("research_and_development"),
                                                    "selling_general_and_administrative": stmt_data.get("selling_general_and_administrative"),
                                                    "operating_income": stmt_data.get("operating_income"),
                                                    "interest_expense": stmt_data.get("interest_expense"),
                                                    "interest_income": stmt_data.get("interest_income"),
                                                    "other_income_expense": stmt_data.get("other_income_expense"),
                                                    "income_before_tax": stmt_data.get("income_before_tax"),
                                                    "income_tax_expense": stmt_data.get("income_tax_expense"),
                                                    "net_income": stmt_data.get("net_income"),
                                                    "earnings_per_share_basic": stmt_data.get("earnings_per_share_basic"),
                                                    "earnings_per_share_diluted": stmt_data.get("earnings_per_share_diluted"),
                                                }
                                            )
                                            
                                            if was_created:
                                                created_count += 1
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
                                    
                                    created += created_count

                                    # Progress reporting every 10 companies for live progress bar
                                    # Show live progress bar with timing
                                    if files_processed % 10 == 0 or files_processed == (limit or len(files)):
                                        total_items = limit or len(files)
                                        percentage = min(100, (files_processed / total_items) * 100)
                                        bar_length = 50
                                        filled_length = int(bar_length * percentage / 100)
                                        bar = "█" * filled_length + "░" * (bar_length - filled_length)
                                        
                                        # Calculate timing metrics
                                        elapsed_time = time.time() - start_time
                                        if files_processed > 0:
                                            avg_time_per_file = elapsed_time / files_processed
                                            remaining_files = total_items - files_processed
                                            estimated_remaining = remaining_files * avg_time_per_file
                                            
                                            # Format time as mm:ss
                                            elapsed_min, elapsed_sec = divmod(int(elapsed_time), 60)
                                            remaining_min, remaining_sec = divmod(int(estimated_remaining), 60)
                                            
                                            progress_line = f"\r📈  Progress: [{bar}] {percentage:.1f}% ({files_processed:,}/{total_items:,}) | ⏱️ {elapsed_min:02d}:{elapsed_sec:02d} elapsed | ⏳ {remaining_min:02d}:{remaining_sec:02d} remaining\r"
                                        else:
                                            progress_line = f"\r📈  Progress: [{bar}] {percentage:.1f}% ({files_processed:,}/{total_items:,})\r"
                                        
                                        self.stdout.write(progress_line, ending="\r")

                                    # Only increment processed counter for successful processing
                                    if statements:
                                        processed += 1
                                        self._processed_count = processed  # Update for timing decorator

                                    if processed % 100 == 0:
                                        self.stdout.write(
                                            f"  Processed {processed} companies ({created} created, {updated} updated)..."
                                        )

                            # Handle individual file processing errors gracefully
                            except Exception as e:
                                failed += 1
                                self.stdout.write(
                                    self.style.WARNING(f"  Error processing {filename}: {e}")
                                )

                # Final summary report
                total_processed = limit or len(files)
                # Show final completed progress bar
                bar_length = 50
                bar = '█' * bar_length  # Full bar
                self.stdout.write(f"\r📈  Progress: [{bar}] 100.0% ({files_processed:,}/{total_processed:,}) | ✅ Complete!")
                self.stdout.write("")  # New line after progress bar
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Files processed: {files_processed} total, "
                        f"{processed} companies with data, "
                        f"{created} created, {updated} updated, {failed} failed, "
                        f"{skipped_no_match} skipped (no matching ticker)."
                    )
                )

        except Exception as e:
            # Handle ZIP processing errors
            self.stderr.write(self.style.ERROR(f"Error processing ZIP: {e}"))

