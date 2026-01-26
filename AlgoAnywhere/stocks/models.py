from django.db import models


class Stock(models.Model):
    """Stock with ticker, name, market capital (USD), and sector."""

    ticker = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    market_cap = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Market capitalization in USD",
    )
    sector = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        ordering = ["ticker"]
        verbose_name = "Stock"
        verbose_name_plural = "Stocks"

    def __str__(self):
        return f"{self.ticker} — {self.name}"


class IncomeStatement(models.Model):
    """Income statement data from SEC EDGAR filings."""

    stock = models.ForeignKey(
        Stock, on_delete=models.CASCADE, related_name="income_statements", db_index=True
    )
    period_end_date = models.DateField(help_text="Period end date (YYYY-MM-DD)")
    fiscal_year = models.IntegerField(db_index=True)
    fiscal_quarter = models.IntegerField(
        null=True, blank=True, help_text="1-4 for quarterly, null for annual"
    )
    form_type = models.CharField(
        max_length=10, help_text="10-K, 10-Q, etc.", null=True, blank=True
    )

    # Revenue
    revenue = models.BigIntegerField(
        null=True, blank=True, help_text="Total revenue (USD)"
    )
    cost_of_revenue = models.BigIntegerField(
        null=True, blank=True, help_text="Cost of goods sold / services (USD)"
    )
    gross_profit = models.BigIntegerField(null=True, blank=True, help_text="Gross profit (USD)")

    # Operating expenses
    operating_expenses = models.BigIntegerField(
        null=True, blank=True, help_text="Total operating expenses (USD)"
    )
    research_and_development = models.BigIntegerField(
        null=True, blank=True, help_text="R&D expenses (USD)"
    )
    selling_general_and_administrative = models.BigIntegerField(
        null=True, blank=True, help_text="SG&A expenses (USD)"
    )

    # Operating income
    operating_income = models.BigIntegerField(
        null=True, blank=True, help_text="Operating income/loss (USD)"
    )

    # Other income/expenses
    interest_expense = models.BigIntegerField(
        null=True, blank=True, help_text="Interest expense (USD)"
    )
    interest_income = models.BigIntegerField(
        null=True, blank=True, help_text="Interest income (USD)"
    )
    other_income_expense = models.BigIntegerField(
        null=True, blank=True, help_text="Other income/expense (USD)"
    )

    # Income before tax
    income_before_tax = models.BigIntegerField(
        null=True, blank=True, help_text="Income before tax (USD)"
    )
    income_tax_expense = models.BigIntegerField(
        null=True, blank=True, help_text="Income tax expense/benefit (USD)"
    )

    # Net income
    net_income = models.BigIntegerField(
        null=True, blank=True, help_text="Net income/loss (USD)"
    )

    # EPS
    earnings_per_share_basic = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True, help_text="EPS basic"
    )
    earnings_per_share_diluted = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True, help_text="EPS diluted"
    )

    # Metadata
    filing_date = models.DateField(null=True, blank=True, help_text="SEC filing date")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["stock", "-fiscal_year", "-fiscal_quarter", "-period_end_date"]
        unique_together = [
            ["stock", "period_end_date", "fiscal_year", "fiscal_quarter"]
        ]
        verbose_name = "Income Statement"
        verbose_name_plural = "Income Statements"
        indexes = [
            models.Index(fields=["stock", "-fiscal_year", "-fiscal_quarter"]),
            models.Index(fields=["period_end_date"]),
        ]

    def __str__(self):
        q = f"Q{self.fiscal_quarter}" if self.fiscal_quarter else "Annual"
        return f"{self.stock.ticker} — {self.fiscal_year} {q} — {self.period_end_date}"


class BalanceSheet(models.Model):
    """Balance sheet data from SEC EDGAR filings."""

    stock = models.ForeignKey(
        Stock, on_delete=models.CASCADE, related_name="balance_sheets", db_index=True
    )
    period_end_date = models.DateField(help_text="Period end date (YYYY-MM-DD)")
    fiscal_year = models.IntegerField(db_index=True)
    fiscal_quarter = models.IntegerField(
        null=True, blank=True, help_text="1-4 for quarterly, null for annual"
    )
    form_type = models.CharField(
        max_length=10, help_text="10-K, 10-Q, etc.", null=True, blank=True
    )

    # Assets
    cash_and_cash_equivalents = models.BigIntegerField(
        null=True, blank=True, help_text="Cash and cash equivalents (USD)"
    )
    short_term_investments = models.BigIntegerField(
        null=True, blank=True, help_text="Short-term investments (USD)"
    )
    accounts_receivable = models.BigIntegerField(
        null=True, blank=True, help_text="Accounts receivable (USD)"
    )
    inventory = models.BigIntegerField(
        null=True, blank=True, help_text="Inventory (USD)"
    )
    other_current_assets = models.BigIntegerField(
        null=True, blank=True, help_text="Other current assets (USD)"
    )
    total_current_assets = models.BigIntegerField(
        null=True, blank=True, help_text="Total current assets (USD)"
    )
    property_plant_equipment = models.BigIntegerField(
        null=True, blank=True, help_text="Property, plant and equipment (USD)"
    )
    goodwill = models.BigIntegerField(
        null=True, blank=True, help_text="Goodwill (USD)"
    )
    intangible_assets = models.BigIntegerField(
        null=True, blank=True, help_text="Intangible assets (USD)"
    )
    long_term_investments = models.BigIntegerField(
        null=True, blank=True, help_text="Long-term investments (USD)"
    )
    other_non_current_assets = models.BigIntegerField(
        null=True, blank=True, help_text="Other non-current assets (USD)"
    )
    total_non_current_assets = models.BigIntegerField(
        null=True, blank=True, help_text="Total non-current assets (USD)"
    )
    total_assets = models.BigIntegerField(
        null=True, blank=True, help_text="Total assets (USD)"
    )

    # Liabilities
    accounts_payable = models.BigIntegerField(
        null=True, blank=True, help_text="Accounts payable (USD)"
    )
    short_term_debt = models.BigIntegerField(
        null=True, blank=True, help_text="Short-term debt (USD)"
    )
    other_current_liabilities = models.BigIntegerField(
        null=True, blank=True, help_text="Other current liabilities (USD)"
    )
    total_current_liabilities = models.BigIntegerField(
        null=True, blank=True, help_text="Total current liabilities (USD)"
    )
    long_term_debt = models.BigIntegerField(
        null=True, blank=True, help_text="Long-term debt (USD)"
    )
    other_non_current_liabilities = models.BigIntegerField(
        null=True, blank=True, help_text="Other non-current liabilities (USD)"
    )
    total_non_current_liabilities = models.BigIntegerField(
        null=True, blank=True, help_text="Total non-current liabilities (USD)"
    )
    total_liabilities = models.BigIntegerField(
        null=True, blank=True, help_text="Total liabilities (USD)"
    )

    # Equity
    common_stock = models.BigIntegerField(
        null=True, blank=True, help_text="Common stock (USD)"
    )
    retained_earnings = models.BigIntegerField(
        null=True, blank=True, help_text="Retained earnings (USD)"
    )
    additional_paid_in_capital = models.BigIntegerField(
        null=True, blank=True, help_text="Additional paid-in capital (USD)"
    )
    other_equity = models.BigIntegerField(
        null=True, blank=True, help_text="Other equity (USD)"
    )
    total_equity = models.BigIntegerField(
        null=True, blank=True, help_text="Total equity (USD)"
    )
    total_liabilities_and_equity = models.BigIntegerField(
        null=True, blank=True, help_text="Total liabilities and equity (USD)"
    )

    # Metadata
    filing_date = models.DateField(null=True, blank=True, help_text="SEC filing date")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["stock", "-fiscal_year", "-fiscal_quarter", "-period_end_date"]
        unique_together = [
            ["stock", "period_end_date", "fiscal_year", "fiscal_quarter"]
        ]
        verbose_name = "Balance Sheet"
        verbose_name_plural = "Balance Sheets"
        indexes = [
            models.Index(fields=["stock", "-fiscal_year", "-fiscal_quarter"]),
            models.Index(fields=["period_end_date"]),
        ]

    def __str__(self):
        q = f"Q{self.fiscal_quarter}" if self.fiscal_quarter else "Annual"
        return f"{self.stock.ticker} — {self.fiscal_year} {q} — {self.period_end_date}"


class CashFlowStatement(models.Model):
    """Cash flow statement data from SEC EDGAR filings."""

    stock = models.ForeignKey(
        Stock, on_delete=models.CASCADE, related_name="cash_flow_statements", db_index=True
    )
    period_end_date = models.DateField(help_text="Period end date (YYYY-MM-DD)")
    fiscal_year = models.IntegerField(db_index=True)
    fiscal_quarter = models.IntegerField(
        null=True, blank=True, help_text="1-4 for quarterly, null for annual"
    )
    form_type = models.CharField(
        max_length=10, help_text="10-K, 10-Q, etc.", null=True, blank=True
    )

    # Operating activities
    net_income = models.BigIntegerField(
        null=True, blank=True, help_text="Net income (USD)"
    )
    depreciation_amortization = models.BigIntegerField(
        null=True, blank=True, help_text="Depreciation and amortization (USD)"
    )
    accounts_receivable_change = models.BigIntegerField(
        null=True, blank=True, help_text="Change in accounts receivable (USD)"
    )
    inventory_change = models.BigIntegerField(
        null=True, blank=True, help_text="Change in inventory (USD)"
    )
    accounts_payable_change = models.BigIntegerField(
        null=True, blank=True, help_text="Change in accounts payable (USD)"
    )
    other_working_capital_change = models.BigIntegerField(
        null=True, blank=True, help_text="Other working capital changes (USD)"
    )
    other_non_cash_items = models.BigIntegerField(
        null=True, blank=True, help_text="Other non-cash items (USD)"
    )
    net_cash_from_operating_activities = models.BigIntegerField(
        null=True, blank=True, help_text="Net cash from operating activities (USD)"
    )

    # Investing activities
    capital_expenditures = models.BigIntegerField(
        null=True, blank=True, help_text="Capital expenditures (USD)"
    )
    acquisitions = models.BigIntegerField(
        null=True, blank=True, help_text="Acquisitions, net (USD)"
    )
    investments_purchased = models.BigIntegerField(
        null=True, blank=True, help_text="Investments purchased (USD)"
    )
    investments_sold = models.BigIntegerField(
        null=True, blank=True, help_text="Investments sold/matured (USD)"
    )
    other_investing_activities = models.BigIntegerField(
        null=True, blank=True, help_text="Other investing activities (USD)"
    )
    net_cash_from_investing_activities = models.BigIntegerField(
        null=True, blank=True, help_text="Net cash from investing activities (USD)"
    )

    # Financing activities
    debt_issued = models.BigIntegerField(
        null=True, blank=True, help_text="Debt issued (USD)"
    )
    debt_repayment = models.BigIntegerField(
        null=True, blank=True, help_text="Debt repayment (USD)"
    )
    common_stock_issued = models.BigIntegerField(
        null=True, blank=True, help_text="Common stock issued (USD)"
    )
    common_stock_repurchased = models.BigIntegerField(
        null=True, blank=True, help_text="Common stock repurchased (USD)"
    )
    dividends_paid = models.BigIntegerField(
        null=True, blank=True, help_text="Dividends paid (USD)"
    )
    other_financing_activities = models.BigIntegerField(
        null=True, blank=True, help_text="Other financing activities (USD)"
    )
    net_cash_from_financing_activities = models.BigIntegerField(
        null=True, blank=True, help_text="Net cash from financing activities (USD)"
    )

    # Cash flow summary
    net_change_in_cash = models.BigIntegerField(
        null=True, blank=True, help_text="Net change in cash (USD)"
    )
    cash_at_beginning_of_period = models.BigIntegerField(
        null=True, blank=True, help_text="Cash at beginning of period (USD)"
    )
    cash_at_end_of_period = models.BigIntegerField(
        null=True, blank=True, help_text="Cash at end of period (USD)"
    )

    # Metadata
    filing_date = models.DateField(null=True, blank=True, help_text="SEC filing date")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["stock", "-fiscal_year", "-fiscal_quarter", "-period_end_date"]
        unique_together = [
            ["stock", "period_end_date", "fiscal_year", "fiscal_quarter"]
        ]
        verbose_name = "Cash Flow Statement"
        verbose_name_plural = "Cash Flow Statements"
        indexes = [
            models.Index(fields=["stock", "-fiscal_year", "-fiscal_quarter"]),
            models.Index(fields=["period_end_date"]),
        ]

    def __str__(self):
        q = f"Q{self.fiscal_quarter}" if self.fiscal_quarter else "Annual"
        return f"{self.stock.ticker} — {self.fiscal_year} {q} — {self.period_end_date}"


class DailyPriceData(models.Model):
    """Daily price data from Yahoo Finance with OHLCV data."""
    
    stock = models.ForeignKey(
        Stock, on_delete=models.CASCADE, related_name="daily_prices", db_index=True
    )
    date = models.DateField(help_text="Trading date (YYYY-MM-DD)")
    open_price = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True, help_text="Opening price"
    )
    high_price = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True, help_text="Highest price"
    )
    low_price = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True, help_text="Lowest price"
    )
    close_price = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True, help_text="Closing price"
    )
    adjusted_close = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True, help_text="Adjusted closing price"
    )
    volume = models.BigIntegerField(
        null=True, blank=True, help_text="Trading volume"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["stock", "-date"]
        unique_together = [["stock", "date"]]
        verbose_name = "Daily Price Data"
        verbose_name_plural = "Daily Price Data"
        indexes = [
            models.Index(fields=["stock", "-date"]),
            models.Index(fields=["date"]),
        ]

    def __str__(self):
        return f"{self.stock.ticker} — {self.date} — ${self.close_price}"
