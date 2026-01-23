from django.contrib import admin

from .models import IncomeStatement, BalanceSheet, CashFlowStatement, Stock


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
    list_filter = ("fiscal_year", "form_type", "fiscal_quarter")  # Removed "stock" to avoid too many entries
    search_fields = ("stock__ticker", "stock__name")
    ordering = ("-fiscal_year", "-fiscal_quarter", "stock")
    raw_id_fields = ("stock",)


@admin.register(BalanceSheet)
class BalanceSheetAdmin(admin.ModelAdmin):
    list_display = (
        "stock",
        "fiscal_year",
        "fiscal_quarter",
        "period_end_date",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "form_type",
    )
    list_filter = ("fiscal_year", "form_type", "fiscal_quarter")  # Removed "stock" to avoid too many entries
    search_fields = ("stock__ticker", "stock__name")
    ordering = ("-fiscal_year", "-fiscal_quarter", "stock")
    raw_id_fields = ("stock",)


@admin.register(CashFlowStatement)
class CashFlowStatementAdmin(admin.ModelAdmin):
    list_display = (
        "stock",
        "fiscal_year",
        "fiscal_quarter",
        "period_end_date",
        "net_cash_from_operating_activities",
        "net_cash_from_investing_activities",
        "net_cash_from_financing_activities",
        "net_change_in_cash",
        "form_type",
    )
    list_filter = ("fiscal_year", "form_type", "fiscal_quarter")  # Removed "stock" to avoid too many entries
    search_fields = ("stock__ticker", "stock__name")
    ordering = ("-fiscal_year", "-fiscal_quarter", "stock")
    raw_id_fields = ("stock",)
