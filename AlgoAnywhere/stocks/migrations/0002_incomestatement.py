# Generated manually for IncomeStatement model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stocks", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="IncomeStatement",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("period_end_date", models.DateField(help_text="Period end date (YYYY-MM-DD)")),
                ("fiscal_year", models.IntegerField(db_index=True)),
                (
                    "fiscal_quarter",
                    models.IntegerField(
                        blank=True, help_text="1-4 for quarterly, null for annual", null=True
                    ),
                ),
                (
                    "form_type",
                    models.CharField(
                        blank=True, help_text="10-K, 10-Q, etc.", max_length=10, null=True
                    ),
                ),
                (
                    "revenue",
                    models.BigIntegerField(blank=True, help_text="Total revenue (USD)", null=True),
                ),
                (
                    "cost_of_revenue",
                    models.BigIntegerField(
                        blank=True, help_text="Cost of goods sold / services (USD)", null=True
                    ),
                ),
                (
                    "gross_profit",
                    models.BigIntegerField(blank=True, help_text="Gross profit (USD)", null=True),
                ),
                (
                    "operating_expenses",
                    models.BigIntegerField(
                        blank=True, help_text="Total operating expenses (USD)", null=True
                    ),
                ),
                (
                    "research_and_development",
                    models.BigIntegerField(blank=True, help_text="R&D expenses (USD)", null=True),
                ),
                (
                    "selling_general_and_administrative",
                    models.BigIntegerField(blank=True, help_text="SG&A expenses (USD)", null=True),
                ),
                (
                    "operating_income",
                    models.BigIntegerField(
                        blank=True, help_text="Operating income/loss (USD)", null=True
                    ),
                ),
                (
                    "interest_expense",
                    models.BigIntegerField(blank=True, help_text="Interest expense (USD)", null=True),
                ),
                (
                    "interest_income",
                    models.BigIntegerField(blank=True, help_text="Interest income (USD)", null=True),
                ),
                (
                    "other_income_expense",
                    models.BigIntegerField(
                        blank=True, help_text="Other income/expense (USD)", null=True
                    ),
                ),
                (
                    "income_before_tax",
                    models.BigIntegerField(
                        blank=True, help_text="Income before tax (USD)", null=True
                    ),
                ),
                (
                    "income_tax_expense",
                    models.BigIntegerField(
                        blank=True, help_text="Income tax expense/benefit (USD)", null=True
                    ),
                ),
                (
                    "net_income",
                    models.BigIntegerField(blank=True, help_text="Net income/loss (USD)", null=True),
                ),
                (
                    "earnings_per_share_basic",
                    models.DecimalField(
                        blank=True,
                        decimal_places=4,
                        help_text="EPS basic",
                        max_digits=10,
                        null=True,
                    ),
                ),
                (
                    "earnings_per_share_diluted",
                    models.DecimalField(
                        blank=True,
                        decimal_places=4,
                        help_text="EPS diluted",
                        max_digits=10,
                        null=True,
                    ),
                ),
                (
                    "filing_date",
                    models.DateField(blank=True, help_text="SEC filing date", null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "stock",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=models.CASCADE,
                        related_name="income_statements",
                        to="stocks.stock",
                    ),
                ),
            ],
            options={
                "verbose_name": "Income Statement",
                "verbose_name_plural": "Income Statements",
                "ordering": ["stock", "-fiscal_year", "-fiscal_quarter", "-period_end_date"],
            },
        ),
        migrations.AddIndex(
            model_name="incomestatement",
            index=models.Index(
                fields=["stock", "-fiscal_year", "-fiscal_quarter"],
                name="stocks_inco_stock_i_abc123_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="incomestatement",
            index=models.Index(fields=["period_end_date"], name="stocks_inco_period__def456_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="incomestatement",
            unique_together={("stock", "period_end_date", "fiscal_year", "fiscal_quarter")},
        ),
    ]
