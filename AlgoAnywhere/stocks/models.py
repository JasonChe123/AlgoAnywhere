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
