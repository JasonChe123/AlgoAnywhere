from django.contrib import admin
from .models import (
    Portfolio, Position, Trade, PortfolioSnapshot, StrategyParameter,
    EquityLongShortPortfolio, EquityUniverse, FactorScore, 
    BasketOrder, BasketOrderItem, BacktestResult
)


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ("name", "strategy_type", "user", "is_backtest", "initial_capital", "created_at")
    list_filter = ("strategy_type", "is_backtest", "created_at")
    search_fields = ("name", "user__username")
    ordering = ("-created_at",)


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("portfolio", "stock", "quantity", "entry_price", "current_price", "is_active", "entry_date")
    list_filter = ("is_active", "entry_date")
    search_fields = ("portfolio__name", "stock__ticker")
    ordering = ("-entry_date",)
    raw_id_fields = ("portfolio", "stock")


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ("portfolio", "stock", "trade_type", "quantity", "price", "trade_date")
    list_filter = ("trade_type", "trade_date")
    search_fields = ("portfolio__name", "stock__ticker")
    ordering = ("-trade_date",)
    raw_id_fields = ("portfolio", "stock")


@admin.register(PortfolioSnapshot)
class PortfolioSnapshotAdmin(admin.ModelAdmin):
    list_display = ("portfolio", "date", "total_value", "cash_balance", "daily_return")
    list_filter = ("date",)
    search_fields = ("portfolio__name",)
    ordering = ("-date",)
    raw_id_fields = ("portfolio",)


@admin.register(EquityLongShortPortfolio)
class EquityLongShortPortfolioAdmin(admin.ModelAdmin):
    list_display = ("name", "universe_type", "rebalance_frequency", "beta_neutral", "sector_neutral", "created_at")
    list_filter = ("universe_type", "rebalance_frequency", "beta_neutral", "sector_neutral", "created_at")
    search_fields = ("name", "user__username")
    ordering = ("-created_at",)


@admin.register(EquityUniverse)
class EquityUniverseAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "stocks_count", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name", "user__username")
    ordering = ("name",)
    raw_id_fields = ("user",)
    
    def stocks_count(self, obj):
        return obj.stocks.count()
    stocks_count.short_description = "Stocks Count"


@admin.register(FactorScore)
class FactorScoreAdmin(admin.ModelAdmin):
    list_display = ("portfolio", "stock", "score_date", "composite_score", "universe_rank", "decile")
    list_filter = ("score_date", "decile")
    search_fields = ("portfolio__name", "stock__ticker")
    ordering = ("-score_date", "-composite_score")
    raw_id_fields = ("portfolio", "stock")


@admin.register(BasketOrder)
class BasketOrderAdmin(admin.ModelAdmin):
    list_display = ("portfolio", "order_date", "status", "total_orders", "estimated_notional", "created_at")
    list_filter = ("status", "order_date", "created_at")
    search_fields = ("portfolio__name",)
    ordering = ("-order_date",)
    raw_id_fields = ("portfolio",)


@admin.register(BasketOrderItem)
class BasketOrderItemAdmin(admin.ModelAdmin):
    list_display = ("basket_order", "stock", "action", "quantity", "target_weight", "estimated_notional")
    list_filter = ("action",)
    search_fields = ("basket_order__portfolio__name", "stock__ticker")
    ordering = ("-estimated_notional",)
    raw_id_fields = ("basket_order", "stock")


@admin.register(BacktestResult)
class BacktestResultAdmin(admin.ModelAdmin):
    list_display = ("portfolio", "total_return", "annualized_return", "sharpe_ratio", "max_drawdown", "volatility")
    list_filter = ("portfolio__strategy_type",)
    search_fields = ("portfolio__name",)
    ordering = ("-portfolio__created_at",)
    raw_id_fields = ("portfolio",)


@admin.register(StrategyParameter)
class StrategyParameterAdmin(admin.ModelAdmin):
    list_display = ("portfolio",)
    search_fields = ("portfolio__name",)
    raw_id_fields = ("portfolio",)
