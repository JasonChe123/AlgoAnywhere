"""
Django management command to download and process SEC EDGAR financial statement data.

This command downloads SEC company facts data from the EDGAR database and
extracts quarterly and annual financial statement information (income statements,
balance sheets, and cash flow statements) for stocks in the database.

Usage:
    python manage.py update_earning_reports --bulk [--from_local] [--limit=N]

Options:
    --bulk: Download bulk companyfacts.zip and process all companies
    --from_local: Use local files instead of downloading
    --limit: Limit number of companies to process (for testing)
"""

import json
import os
import time
import zipfile
from datetime import datetime
from functools import wraps
from io import BytesIO

import pandas as pd
import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from stocks.models import IncomeStatement, BalanceSheet, CashFlowStatement, Stock


def timing_decorator(func):
    """
    Decorator to measure and report execution time with progress prediction and live progress bar.

    Provides timing information, estimates completion time based on current progress,
    and displays a live progress bar showing completion percentage.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        start_time = time.time()
        self.stdout.write(f"⏱️  Starting function '{func.__name__}' at {datetime.now().strftime('%H:%M:%S')}\n\n")
        result = func(self, *args, **kwargs)
        time_used = time.time() - start_time
        self.stdout.write(f"\n⏱️  Completed function '{func.__name__}' in {int(time_used//60)}m {int(time_used%60)}s")

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

# US-GAAP concept mappings to BalanceSheet model fields
BALANCE_SHEET_CONCEPT_MAP = {
    # Assets
    "CashAndCashEquivalentsAtCarryingValue": "cash_and_cash_equivalents",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": "cash_and_cash_equivalents",
    "ShortTermInvestments": "short_term_investments",
    "AccountsReceivableNetCurrent": "accounts_receivable",
    "InventoryNet": "inventory",
    "OtherCurrentAssets": "other_current_assets",
    "AssetsCurrent": "total_current_assets",
    "PropertyPlantAndEquipmentNet": "property_plant_equipment",
    "Goodwill": "goodwill",
    "IntangibleAssetsNetExcludingGoodwill": "intangible_assets",
    "LongTermInvestments": "long_term_investments",
    "OtherNoncurrentAssets": "other_non_current_assets",
    "AssetsNoncurrent": "total_non_current_assets",
    "Assets": "total_assets",
    
    # Liabilities
    "AccountsPayableCurrent": "accounts_payable",
    "ShortTermDebt": "short_term_debt",
    "OtherCurrentLiabilities": "other_current_liabilities",
    "LiabilitiesCurrent": "total_current_liabilities",
    "LongTermDebt": "long_term_debt",
    "OtherNoncurrentLiabilities": "other_non_current_liabilities",
    "LiabilitiesNoncurrent": "total_non_current_liabilities",
    "Liabilities": "total_liabilities",
    
    # Equity
    "CommonStockValue": "common_stock",
    "RetainedEarningsAccumulatedDeficit": "retained_earnings",
    "AdditionalPaidInCapital": "additional_paid_in_capital",
    "OtherEquity": "other_equity",
    "StockholdersEquity": "total_equity",
    "LiabilitiesAndStockholdersEquity": "total_liabilities_and_equity",
}

# US-GAAP concept mappings to CashFlowStatement model fields
CASH_FLOW_CONCEPT_MAP = {
    # Operating activities
    "NetIncomeLoss": "net_income",
    "DepreciationDepletionAndAmortization": "depreciation_amortization",
    "IncreaseDecreaseInAccountsReceivable": "accounts_receivable_change",
    "IncreaseDecreaseInInventory": "inventory_change",
    "IncreaseDecreaseInAccountsPayable": "accounts_payable_change",
    "OtherWorkingCapitalChanges": "other_working_capital_change",
    "OtherNoncashItems": "other_non_cash_items",
    "NetCashProvidedByUsedInOperatingActivities": "net_cash_from_operating_activities",
    
    # Investing activities
    "PaymentsToAcquirePropertyPlantAndEquipment": "capital_expenditures",
    "AcquisitionsDispositionsOfBusinessesNet": "acquisitions",
    "PurchasesOfInvestments": "investments_purchased",
    "SalesMaturitiesOfInvestmentsSecurities": "investments_sold",
    "OtherInvestingActivities": "other_investing_activities",
    "NetCashProvidedByUsedInInvestingActivities": "net_cash_from_investing_activities",
    
    # Financing activities
    "ProceedsFromDebt": "debt_issued",
    "RepaymentsOfDebt": "debt_repayment",
    "ProceedsFromIssuanceOfCommonStock": "common_stock_issued",
    "PaymentsForRepurchaseOfCommonStock": "common_stock_repurchased",
    "DividendsPaid": "dividends_paid",
    "OtherFinancingActivities": "other_financing_activities",
    "NetCashProvidedByUsedInFinancingActivities": "net_cash_from_financing_activities",
    
    # Cash flow summary
    "CashAndCashEquivalentsPeriodIncreaseDecrease": "net_change_in_cash",
    "CashAndCashEquivalentsAtBeginningOfPeriod": "cash_at_beginning_of_period",
    "CashAndCashEquivalentsAtEndOfPeriod": "cash_at_end_of_period",
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
        - Fiscal quarter is determined by:
          1. Period duration (if start date available)
          2. Form type and end date (for balance sheets without start dates)
          3. End date month for cumulative cash flow periods
        - Quarterly periods are typically 60-120 days
        - Cumulative periods (>120 days) use end date month to infer quarter
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
            elif days > 120:  # Cumulative period (common for cash flow)
                # For cumulative periods, infer quarter from end date month
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
    else:
        # For balance sheets and other point-in-time data without start dates,
        # infer quarter from form type and end date
        form_type = fact.get("form", "")
        if form_type == "10-Q":
            # Quarterly filing - infer quarter from end date
            month = end_date.month
            if month in (3, 4, 5):
                fiscal_quarter = 1
            elif month in (6, 7, 8):
                fiscal_quarter = 2
            elif month in (9, 10, 11):
                fiscal_quarter = 3
            else:
                fiscal_quarter = 4
        elif form_type == "10-K":
            # Annual filing - keep as None (annual)
            fiscal_quarter = None

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

                # Create a unique key for fiscal year and quarter only
                # Use 0 as sentinel for NULL fiscal_quarter to ensure uniqueness
                actual_quarter = fiscal_quarter if fiscal_quarter is not None else 0
                key = (fiscal_year, actual_quarter)
                
                if key not in period_data:
                    period_data[key] = {
                        "period_end_date": end_date,
                        "fiscal_year": fiscal_year,
                        "fiscal_quarter": fiscal_quarter,  # Keep original None for database
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


def _extract_balance_sheet_data(company_facts_json):
    """
    Extract balance sheet data from SEC company facts JSON.
    
    This function processes SEC company facts data and extracts quarterly/annual
    balance sheet information, grouping by fiscal period and selecting the most
    recent filing data for each period.
    
    Args:
        company_facts_json (dict): SEC company facts JSON data
        
    Returns:
        list: List of dictionaries containing balance sheet data for each fiscal period
        
    Processing Logic:
        1. Maps US-GAAP concepts to database fields using BALANCE_SHEET_CONCEPT_MAP
        2. Groups data by fiscal year, quarter, and form type to prevent duplicates
        3. For each fiscal period, uses the most recent filing data
        4. Filters out future dates and incomplete records
        5. Only includes records with meaningful financial data (assets or liabilities)
    """
    facts = company_facts_json.get("facts", {})
    us_gaap = facts.get("us-gaap", {})
    if not us_gaap:
        return []

    # Group by fiscal year, quarter, and form type to prevent duplicates
    period_data = {}

    for concept_name, concept_data in us_gaap.items():
        field_name = BALANCE_SHEET_CONCEPT_MAP.get(concept_name)
        if not field_name:
            continue

        units = concept_data.get("units", {})
        for unit_key, unit_facts in units.items():
            # Only process USD amounts
            if "USD" not in unit_key:
                continue

            for fact in unit_facts:
                fiscal_year, fiscal_quarter, end_date = _parse_period(fact)
                # Filter out future dates and invalid periods
                if not end_date or fiscal_year > datetime.now().year + 1:
                    continue

                # Create a unique key for fiscal year and quarter only
                actual_quarter = fiscal_quarter if fiscal_quarter is not None else 0
                key = (fiscal_year, actual_quarter)
                
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
                if val is not None and val != 0:
                    # Use most recent filing data for each fiscal period
                    existing_val = period_data[key].get(field_name)
                    existing_filing_date = period_data[key].get("filing_date")
                    current_filing_date = fact.get("filed")
                    
                    # Use the most recent filing data
                    if (existing_val is None or 
                        (current_filing_date and existing_filing_date and current_filing_date > existing_filing_date)):
                        
                        # All balance sheet values as integers
                        period_data[key][field_name] = int(val)
                        
                        # Update filing date and period end date if more recent
                        if current_filing_date:
                            period_data[key]["filing_date"] = current_filing_date
                        if end_date > period_data[key]["period_end_date"]:
                            period_data[key]["period_end_date"] = end_date

    # Convert to list and filter out incomplete records
    result = []
    for data in period_data.values():
        # Only include records that have at least total assets or total liabilities
        if data.get("total_assets") or data.get("total_liabilities"):
            result.append(data)
    
    return result


def _extract_cash_flow_data(company_facts_json):
    """
    Extract cash flow statement data from SEC company facts JSON.
    
    This function processes SEC company facts data and extracts quarterly/annual
    cash flow information, grouping by fiscal period and selecting the most
    recent filing data for each period.
    
    Args:
        company_facts_json (dict): SEC company facts JSON data
        
    Returns:
        list: List of dictionaries containing cash flow data for each fiscal period
        
    Processing Logic:
        1. Maps US-GAAP concepts to database fields using CASH_FLOW_CONCEPT_MAP
        2. Groups data by fiscal year, quarter, and form type to prevent duplicates
        3. For each fiscal period, uses the most recent filing data
        4. Filters out future dates and incomplete records
        5. Only includes records with meaningful cash flow data
    """
    facts = company_facts_json.get("facts", {})
    us_gaap = facts.get("us-gaap", {})
    if not us_gaap:
        return []

    # Group by fiscal year, quarter, and form type to prevent duplicates
    period_data = {}

    for concept_name, concept_data in us_gaap.items():
        field_name = CASH_FLOW_CONCEPT_MAP.get(concept_name)
        if not field_name:
            continue

        units = concept_data.get("units", {})
        for unit_key, unit_facts in units.items():
            # Only process USD amounts
            if "USD" not in unit_key:
                continue

            for fact in unit_facts:
                fiscal_year, fiscal_quarter, end_date = _parse_period(fact)
                # Filter out future dates and invalid periods
                if not end_date or fiscal_year > datetime.now().year + 1:
                    continue

                # Create a unique key for fiscal year and quarter only
                actual_quarter = fiscal_quarter if fiscal_quarter is not None else 0
                key = (fiscal_year, actual_quarter)
                
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
                if val is not None and val != 0:
                    # Use most recent filing data for each fiscal period
                    existing_val = period_data[key].get(field_name)
                    existing_filing_date = period_data[key].get("filing_date")
                    current_filing_date = fact.get("filed")
                    
                    # Use the most recent filing data
                    if (existing_val is None or 
                        (current_filing_date and existing_filing_date and current_filing_date > existing_filing_date)):
                        
                        # All cash flow values as integers
                        period_data[key][field_name] = int(val)
                        
                        # Update filing date and period end date if more recent
                        if current_filing_date:
                            period_data[key]["filing_date"] = current_filing_date
                        if end_date > period_data[key]["period_end_date"]:
                            period_data[key]["period_end_date"] = end_date

    # Convert to list and filter out incomplete records
    result = []
    for data in period_data.values():
        # Only include records that have meaningful cash flow data
        if (data.get("net_cash_from_operating_activities") or 
            data.get("net_cash_from_investing_activities") or 
            data.get("net_cash_from_financing_activities") or
            data.get("net_change_in_cash")):
            result.append(data)
    
    return result


def _calculate_progress_metrics(files_processed, total_items, start_time):
    """
    Calculate progress bar and timing metrics.
    
    Args:
        files_processed (int): Number of files processed
        total_items (int): Total number of items to process
        start_time (float): Start time for elapsed calculation
        
    Returns:
        dict: Progress metrics including bar, percentage, timing info
    """
    percentage = min(100, (files_processed / total_items) * 100)
    bar_length = 50
    filled_length = int(bar_length * percentage / 100)
    bar = "█" * filled_length + "░" * (bar_length - filled_length)
    
    metrics = {
        'bar': bar,
        'percentage': percentage,
        'files_processed': files_processed,
        'total_items': total_items
    }
    
    if files_processed > 0:
        elapsed_time = time.time() - start_time
        avg_time_per_file = elapsed_time / files_processed
        remaining_files = total_items - files_processed
        estimated_remaining = remaining_files * avg_time_per_file
        
        elapsed_min, elapsed_sec = divmod(int(elapsed_time), 60)
        remaining_min, remaining_sec = divmod(int(estimated_remaining), 60)
        
        metrics.update({
            'elapsed_min': elapsed_min,
            'elapsed_sec': elapsed_sec,
            'remaining_min': remaining_min,
            'remaining_sec': remaining_sec
        })
    
    return metrics


def _format_progress_line(metrics, complete=False):
    """
    Format progress line with bar and timing information.
    
    Args:
        metrics (dict): Progress metrics from _calculate_progress_metrics
        complete (bool): Whether processing is complete
        
    Returns:
        str: Formatted progress line
    """
    if metrics['files_processed'] > 0:
        if complete:
            return (f"\r📈  Progress: [{metrics['bar']}] {metrics['percentage']:.1f}% "
                   f"({metrics['files_processed']:,}/{metrics['total_items']:,}) | "
                   f"⏱️  {metrics['elapsed_min']:02d}:{metrics['elapsed_sec']:02d} elapsed | "
                   f"⏳ {metrics['remaining_min']:02d}:{metrics['remaining_sec']:02d} remaining | ✅ Complete!\r")
        else:
            return (f"\r  📈  Progress: [{metrics['bar']}] {metrics['percentage']:.1f}% "
                   f"({metrics['files_processed']:,}/{metrics['total_items']:,}) | "
                   f"⏱️  {metrics['elapsed_min']:02d}:{metrics['elapsed_sec']:02d} elapsed | "
                   f"⏳ {metrics['remaining_min']:02d}:{metrics['remaining_sec']:02d} remaining\r")
    else:
        return f"\r📈  Progress: [{metrics['bar']}] {metrics['percentage']:.1f}% ({metrics['files_processed']:,}/{metrics['total_items']:,})\r"


def _prepare_income_statements(stock, statements, ticker):
    """
    Prepare income statement objects for bulk creation.
    
    Args:
        stock: Stock object
        statements (list): List of statement data from SEC
        ticker (str): Stock ticker
        
    Returns:
        list: List of IncomeStatement objects ready for bulk creation
    """
    objects_to_create = []
    
    for stmt_data in statements:
        # Parse filing date for database storage
        filing_date_str = stmt_data.get("filing_date")
        filing_date = None
        if filing_date_str:
            try:
                filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass

        # Create IncomeStatement object (don't save yet)
        income_stmt = IncomeStatement(
            stock=stock,
            period_end_date=stmt_data["period_end_date"],
            fiscal_year=stmt_data["fiscal_year"],
            fiscal_quarter=stmt_data.get("fiscal_quarter") or 0,  # Store 0 instead of NULL
            form_type=stmt_data.get("form_type"),
            filing_date=filing_date,
            revenue=stmt_data.get("revenue"),
            cost_of_revenue=stmt_data.get("cost_of_revenue"),
            gross_profit=stmt_data.get("gross_profit"),
            operating_expenses=stmt_data.get("operating_expenses"),
            research_and_development=stmt_data.get("research_and_development"),
            selling_general_and_administrative=stmt_data.get("selling_general_and_administrative"),
            operating_income=stmt_data.get("operating_income"),
            interest_expense=stmt_data.get("interest_expense"),
            interest_income=stmt_data.get("interest_income"),
            other_income_expense=stmt_data.get("other_income_expense"),
            income_before_tax=stmt_data.get("income_before_tax"),
            income_tax_expense=stmt_data.get("income_tax_expense"),
            net_income=stmt_data.get("net_income"),
            earnings_per_share_basic=stmt_data.get("earnings_per_share_basic"),
            earnings_per_share_diluted=stmt_data.get("earnings_per_share_diluted"),
        )
        
        objects_to_create.append(income_stmt)
    
    return objects_to_create


def _prepare_balance_sheets(stock, statements, ticker):
    """
    Prepare balance sheet objects for bulk creation.
    
    Args:
        stock: Stock object
        statements (list): List of statement data from SEC
        ticker (str): Stock ticker
        
    Returns:
        list: List of BalanceSheet objects ready for bulk creation
    """
    objects_to_create = []
    
    for stmt_data in statements:
        # Parse filing date for database storage
        filing_date_str = stmt_data.get("filing_date")
        filing_date = None
        if filing_date_str:
            try:
                filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass

        # Create BalanceSheet object (don't save yet)
        balance_sheet = BalanceSheet(
            stock=stock,
            period_end_date=stmt_data["period_end_date"],
            fiscal_year=stmt_data["fiscal_year"],
            fiscal_quarter=stmt_data.get("fiscal_quarter") or 0,  # Store 0 instead of NULL
            form_type=stmt_data.get("form_type"),
            filing_date=filing_date,
            # Assets
            cash_and_cash_equivalents=stmt_data.get("cash_and_cash_equivalents"),
            short_term_investments=stmt_data.get("short_term_investments"),
            accounts_receivable=stmt_data.get("accounts_receivable"),
            inventory=stmt_data.get("inventory"),
            other_current_assets=stmt_data.get("other_current_assets"),
            total_current_assets=stmt_data.get("total_current_assets"),
            property_plant_equipment=stmt_data.get("property_plant_equipment"),
            goodwill=stmt_data.get("goodwill"),
            intangible_assets=stmt_data.get("intangible_assets"),
            long_term_investments=stmt_data.get("long_term_investments"),
            other_non_current_assets=stmt_data.get("other_non_current_assets"),
            total_non_current_assets=stmt_data.get("total_non_current_assets"),
            total_assets=stmt_data.get("total_assets"),
            # Liabilities
            accounts_payable=stmt_data.get("accounts_payable"),
            short_term_debt=stmt_data.get("short_term_debt"),
            other_current_liabilities=stmt_data.get("other_current_liabilities"),
            total_current_liabilities=stmt_data.get("total_current_liabilities"),
            long_term_debt=stmt_data.get("long_term_debt"),
            other_non_current_liabilities=stmt_data.get("other_non_current_liabilities"),
            total_non_current_liabilities=stmt_data.get("total_non_current_liabilities"),
            total_liabilities=stmt_data.get("total_liabilities"),
            # Equity
            common_stock=stmt_data.get("common_stock"),
            retained_earnings=stmt_data.get("retained_earnings"),
            additional_paid_in_capital=stmt_data.get("additional_paid_in_capital"),
            other_equity=stmt_data.get("other_equity"),
            total_equity=stmt_data.get("total_equity"),
            total_liabilities_and_equity=stmt_data.get("total_liabilities_and_equity"),
        )
        
        objects_to_create.append(balance_sheet)
    
    return objects_to_create


def _prepare_cash_flow_statements(stock, statements, ticker):
    """
    Prepare cash flow statement objects for bulk creation.
    
    Args:
        stock: Stock object
        statements (list): List of statement data from SEC
        ticker (str): Stock ticker
        
    Returns:
        list: List of CashFlowStatement objects ready for bulk creation
    """
    objects_to_create = []
    
    for stmt_data in statements:
        # Parse filing date for database storage
        filing_date_str = stmt_data.get("filing_date")
        filing_date = None
        if filing_date_str:
            try:
                filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass

        # Create CashFlowStatement object (don't save yet)
        cash_flow = CashFlowStatement(
            stock=stock,
            period_end_date=stmt_data["period_end_date"],
            fiscal_year=stmt_data["fiscal_year"],
            fiscal_quarter=stmt_data.get("fiscal_quarter") or 0,  # Store 0 instead of NULL
            form_type=stmt_data.get("form_type"),
            filing_date=filing_date,
            # Operating activities
            net_income=stmt_data.get("net_income"),
            depreciation_amortization=stmt_data.get("depreciation_amortization"),
            accounts_receivable_change=stmt_data.get("accounts_receivable_change"),
            inventory_change=stmt_data.get("inventory_change"),
            accounts_payable_change=stmt_data.get("accounts_payable_change"),
            other_working_capital_change=stmt_data.get("other_working_capital_change"),
            other_non_cash_items=stmt_data.get("other_non_cash_items"),
            net_cash_from_operating_activities=stmt_data.get("net_cash_from_operating_activities"),
            # Investing activities
            capital_expenditures=stmt_data.get("capital_expenditures"),
            acquisitions=stmt_data.get("acquisitions"),
            investments_purchased=stmt_data.get("investments_purchased"),
            investments_sold=stmt_data.get("investments_sold"),
            other_investing_activities=stmt_data.get("other_investing_activities"),
            net_cash_from_investing_activities=stmt_data.get("net_cash_from_investing_activities"),
            # Financing activities
            debt_issued=stmt_data.get("debt_issued"),
            debt_repayment=stmt_data.get("debt_repayment"),
            common_stock_issued=stmt_data.get("common_stock_issued"),
            common_stock_repurchased=stmt_data.get("common_stock_repurchased"),
            dividends_paid=stmt_data.get("dividends_paid"),
            other_financing_activities=stmt_data.get("other_financing_activities"),
            net_cash_from_financing_activities=stmt_data.get("net_cash_from_financing_activities"),
            # Cash flow summary
            net_change_in_cash=stmt_data.get("net_change_in_cash"),
            cash_at_beginning_of_period=stmt_data.get("cash_at_beginning_of_period"),
            cash_at_end_of_period=stmt_data.get("cash_at_end_of_period"),
        )
        
        objects_to_create.append(cash_flow)
    
    return objects_to_create


class Command(BaseCommand):
    """
    Django management command for updating SEC EDGAR financial statement data.
    
    This command downloads SEC company facts data and processes it to populate
    the IncomeStatement, BalanceSheet, and CashFlowStatement models with quarterly 
    and annual financial data.
    """
    help = "Download SEC EDGAR financial statement data. Use --bulk to download bulk ZIP."

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
            cik_ticker_mapper = json.loads(resp_ticker_cik.text)
        else:
            # Use local files for development/testing
            try:
                self.stdout.write(f"  Reading local companyfacts.zip...")
                current_folder = os.path.dirname(os.path.abspath(__file__))
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
        self.stdout.write(f"  Creating {len(stocks_dict)} stock objects from database...")
        
        # Set total items for timing predictions
        self._total_items = limit or 19140  # Total files in ZIP

        # Extract and process ZIP file containing company facts
        try:
            with zipfile.ZipFile(BytesIO(companyfacts_data)) as z:
                files = [f for f in z.namelist() if f.endswith(".json")]
                self.stdout.write(f"  Found {len(files)} company fact files in ZIP")
                
                # Skip existing records check - use bulk_create with ignore_conflicts instead
                self.stdout.write("  Using bulk_create with ignore_conflicts for optimal performance...")
                
                # Initialize counters for progress tracking
                files_processed = 0  # Track actual file progress
                income_created = 0
                balance_sheet_created = 0
                cash_flow_created = 0
                failed = 0
                skipped_no_match = 0
                batch_size = 200  # Process companies in batches for memory efficiency
                income_batch = []  # Collect income statement objects for bulk creation
                balance_sheet_batch = []  # Collect balance sheet objects for bulk creation
                cash_flow_batch = []  # Collect cash flow objects for bulk creation
                
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

                                    # Extract all financial statement data from SEC facts
                                    income_statements = _extract_income_statement_data(data)
                                    balance_sheets = _extract_balance_sheet_data(data)
                                    cash_flow_statements = _extract_cash_flow_data(data)
                                    
                                    # Skip if no data found for any statement type
                                    if not income_statements and not balance_sheets and not cash_flow_statements:
                                        continue

                                    # Prepare income statements for bulk creation
                                    if income_statements:
                                        income_objects = _prepare_income_statements(
                                            stock, income_statements, ticker
                                        )
                                        income_batch.extend(income_objects)
                                    
                                    # Prepare balance sheets for bulk creation
                                    if balance_sheets:
                                        balance_sheet_objects = _prepare_balance_sheets(
                                            stock, balance_sheets, ticker
                                        )
                                        balance_sheet_batch.extend(balance_sheet_objects)
                                    
                                    # Prepare cash flow statements for bulk creation
                                    if cash_flow_statements:
                                        cash_flow_objects = _prepare_cash_flow_statements(
                                            stock, cash_flow_statements, ticker
                                        )
                                        cash_flow_batch.extend(cash_flow_objects)
                                    
                                    # Perform bulk create every 1000 objects or at end of batch
                                    total_batch_size = len(income_batch) + len(balance_sheet_batch) + len(cash_flow_batch)
                                    if total_batch_size >= 1000 or filename == batch_files[-1]:
                                        try:
                                            # Bulk create income statements
                                            if income_batch:
                                                result = IncomeStatement.objects.bulk_create(
                                                    income_batch, 
                                                    batch_size=500,
                                                    ignore_conflicts=True
                                                )
                                                income_created += len(result)
                                                income_batch = []
                                            
                                            # Bulk create balance sheets
                                            if balance_sheet_batch:
                                                result = BalanceSheet.objects.bulk_create(
                                                    balance_sheet_batch,
                                                    batch_size=500,
                                                    ignore_conflicts=True
                                                )
                                                balance_sheet_created += len(result)
                                                balance_sheet_batch = []
                                            
                                            # Bulk create cash flow statements
                                            if cash_flow_batch:
                                                result = CashFlowStatement.objects.bulk_create(
                                                    cash_flow_batch,
                                                    batch_size=500,
                                                    ignore_conflicts=True
                                                )
                                                cash_flow_created += len(result)
                                                cash_flow_batch = []
                                                
                                        except Exception as e:
                                            failed += len(income_batch) + len(balance_sheet_batch) + len(cash_flow_batch)
                                            if failed <= 10:
                                                self.stdout.write(
                                                    self.style.WARNING(f"  Bulk create failed: {e}")
                                                )
                                            # Reset batches even on failure
                                            income_batch = []
                                            balance_sheet_batch = []
                                            cash_flow_batch = []

                                    # Progress reporting with helper functions
                                    total_items = limit or len(files)
                                    metrics = _calculate_progress_metrics(files_processed, total_items, start_time)
                                    progress_line = _format_progress_line(metrics)
                                    self.stdout.write(progress_line, ending="\r")

                            # Handle individual file processing errors gracefully
                            except Exception as e:
                                failed += 1
                                if failed <= 10:
                                    self.stdout.write(
                                        self.style.WARNING(f"  Error processing {filename}: {e}")
                                    )
                
                # Final bulk create for any remaining objects
                try:
                    # Final bulk create for income statements
                    if income_batch:
                        result = IncomeStatement.objects.bulk_create(
                            income_batch, 
                            batch_size=500,
                            ignore_conflicts=True
                        )
                        income_created += len(result)
                    
                    # Final bulk create for balance sheets
                    if balance_sheet_batch:
                        result = BalanceSheet.objects.bulk_create(
                            balance_sheet_batch,
                            batch_size=500,
                            ignore_conflicts=True
                        )
                        balance_sheet_created += len(result)
                    
                    # Final bulk create for cash flow statements
                    if cash_flow_batch:
                        result = CashFlowStatement.objects.bulk_create(
                            cash_flow_batch,
                            batch_size=500,
                            ignore_conflicts=True
                        )
                        cash_flow_created += len(result)
                        
                except Exception as e:
                    failed += len(income_batch) + len(balance_sheet_batch) + len(cash_flow_batch)
                    self.stdout.write(
                        self.style.WARNING(f"  Final bulk create failed: {e}")
                    )

                # Final summary report
                total_items = limit or len(files)
                metrics = _calculate_progress_metrics(files_processed, total_items, start_time)
                progress_line = _format_progress_line(metrics, complete=True)
                self.stdout.write(progress_line)
                self.stdout.write("")  # New line after progress bar
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Files processed: {files_processed} total, "
                        f"{skipped_no_match} files skipped (no matching ticker), "
                        f"{income_created} income statements, "
                        f"{balance_sheet_created} balance sheets, "
                        f"{cash_flow_created} cash flow statements created, "
                        f"{failed} failed."
                    )
                )

        except Exception as e:
            # Handle ZIP processing errors
            self.stderr.write(self.style.ERROR(f"Error processing ZIP: {e}"))
