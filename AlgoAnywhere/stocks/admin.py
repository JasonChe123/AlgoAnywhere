from django.contrib import admin

from .models import IncomeStatement, BalanceSheet, CashFlowStatement, Stock, DailyPriceData


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


@admin.register(DailyPriceData)
class DailyPriceDataAdmin(admin.ModelAdmin):
    list_display = (
        "stock",
        "date",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
    )
    list_filter = ("date",)  # Removed "stock" to avoid too many entries
    search_fields = ("stock__ticker", "stock__name")
    ordering = ("-date", "stock")
    raw_id_fields = ("stock",)
    
    # Add date hierarchy for easier navigation
    date_hierarchy = "date"
    
    # Show millions of records efficiently
    show_full_result_count = False
    
    # Add readonly fields for performance
    readonly_fields = ("created_at", "updated_at")
    
    def get_queryset(self, request):
        # Optimize queries for large datasets
        return super().get_queryset(request).select_related('stock')
    
    def get_readonly_fields(self, request, obj=None):
        # Make most fields readonly for existing records to prevent accidental changes
        if obj:  # Editing existing object
            return ("stock", "date", "open_price", "high_price", "low_price", 
                   "close_price", "adjusted_close", "volume", "created_at", "updated_at")
        return self.readonly_fields
