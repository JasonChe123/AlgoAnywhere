from django.contrib import admin

from .models import IncomeStatement, Stock


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("ticker", "name", "sector", "market_cap")
    list_filter = ("sector",)
    search_fields = ("ticker", "name")
    ordering = ("ticker",)


@admin.register(IncomeStatement)
class IncomeStatementAdmin(admin.ModelAdmin):
    list_display = (
        "stock",
        "fiscal_year",
        "fiscal_quarter",
        "period_end_date",
        "revenue",
        "net_income",
        "form_type",
    )
    list_filter = ("fiscal_year", "form_type", "fiscal_quarter")
    search_fields = ("stock__ticker", "stock__name")
    ordering = ("-fiscal_year", "-fiscal_quarter", "stock")
    raw_id_fields = ("stock",)
