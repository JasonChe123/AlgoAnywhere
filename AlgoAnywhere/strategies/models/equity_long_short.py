"""
Equity Long-Short strategy specific models.

These models extend the base models to support equity long-short strategies
with universe selection, factor scoring, and basket generation.
"""

from django.db import models
from django.contrib.auth.models import User
from stocks.models import Stock
from strategies.models.base import Portfolio


class EquityLongShortPortfolio(Portfolio):
    """
    Extended portfolio model for equity long-short strategies.
    """
    # Universe selection
    universe_type = models.CharField(max_length=20, choices=[
        ('sp500', 'S&P 500'),
        ('russell1000', 'Russell 1000'),
        ('russell2000', 'Russell 2000'),
        ('custom', 'Custom Universe'),
    ], default='sp500')
    
    # Position sizing
    long_target_weight = models.DecimalField(max_digits=5, decimal_places=4, default=0.50)  # 50% long
    short_target_weight = models.DecimalField(max_digits=5, decimal_places=4, default=0.50)  # 50% short
    max_position_weight = models.DecimalField(max_digits=5, decimal_places=4, default=0.05)  # 5% max per position
    
    # Rebalancing
    rebalance_frequency = models.CharField(max_length=20, choices=[
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ], default='monthly')
    
    # Risk management
    beta_neutral = models.BooleanField(default=True)
    sector_neutral = models.BooleanField(default=True)
    max_leverage = models.DecimalField(max_digits=5, decimal_places=2, default=2.0)
    
    class Meta:
        verbose_name = "Equity Long-Short Portfolio"
        verbose_name_plural = "Equity Long-Short Portfolios"


class EquityUniverse(models.Model):
    """
    Custom stock universe for equity strategies.
    """
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    stocks = models.ManyToManyField(Stock, related_name='universes')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Universe criteria
    min_market_cap = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    max_market_cap = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    min_price = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    exclude_etfs = models.BooleanField(default=True)
    exclude_adrs = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.stocks.count()} stocks)"


class FactorScore(models.Model):
    """
    Factor scores for stocks used in equity long-short strategies.
    """
    portfolio = models.ForeignKey(EquityLongShortPortfolio, on_delete=models.CASCADE, related_name='factor_scores')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    score_date = models.DateField()
    
    # Factor scores
    value_score = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    momentum_score = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    quality_score = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    growth_score = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    
    # Composite score
    composite_score = models.DecimalField(max_digits=8, decimal_places=4)
    
    # Ranking
    universe_rank = models.IntegerField()
    decile = models.IntegerField()
    
    class Meta:
        unique_together = ['portfolio', 'stock', 'score_date']
        ordering = ['-composite_score']
    
    def __str__(self):
        return f"{self.stock.ticker} - {self.composite_score:.2f}"


class BasketOrder(models.Model):
    """
    Generated basket orders for broker execution.
    """
    portfolio = models.ForeignKey(EquityLongShortPortfolio, on_delete=models.CASCADE, related_name='basket_orders')
    order_date = models.DateField()
    status = models.CharField(max_length=20, choices=[
        ('generated', 'Generated'),
        ('downloaded', 'Downloaded'),
        ('executed', 'Executed'),
        ('cancelled', 'Cancelled'),
    ], default='generated')
    
    # Order summary
    total_orders = models.IntegerField(default=0)
    long_orders = models.IntegerField(default=0)
    short_orders = models.IntegerField(default=0)
    estimated_notional = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    
    # File generation
    csv_file = models.FileField(upload_to='basket_orders/', null=True, blank=True)
    excel_file = models.FileField(upload_to='basket_orders/', null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-order_date']
    
    def __str__(self):
        return f"Basket Order - {self.order_date} ({self.status})"


class BasketOrderItem(models.Model):
    """
    Individual items within a basket order.
    """
    basket_order = models.ForeignKey(BasketOrder, on_delete=models.CASCADE, related_name='items')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    action = models.CharField(max_length=10)  # 'BUY', 'SELL', 'SHORT', 'COVER'
    quantity = models.IntegerField()
    target_weight = models.DecimalField(max_digits=8, decimal_places=4)
    current_weight = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    
    # Pricing
    last_price = models.DecimalField(max_digits=10, decimal_places=4)
    estimated_notional = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Reasoning
    signal_reason = models.TextField(blank=True)
    factor_scores = models.JSONField(null=True, blank=True)
    
    class Meta:
        ordering = ['-estimated_notional']
    
    def __str__(self):
        return f"{self.action} {abs(self.quantity)} {self.stock.ticker}"


class BacktestResult(models.Model):
    """
    Detailed backtest results for equity long-short strategies.
    """
    portfolio = models.OneToOneField(EquityLongShortPortfolio, on_delete=models.CASCADE, related_name='backtest_result')
    
    # Performance metrics
    total_return = models.DecimalField(max_digits=10, decimal_places=4)
    annualized_return = models.DecimalField(max_digits=10, decimal_places=4)
    sharpe_ratio = models.DecimalField(max_digits=8, decimal_places=4)
    sortino_ratio = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    max_drawdown = models.DecimalField(max_digits=8, decimal_places=4)
    volatility = models.DecimalField(max_digits=8, decimal_places=4)
    
    # Risk metrics
    beta = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    alpha = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    information_ratio = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    
    # Trading statistics
    total_trades = models.IntegerField()
    win_rate = models.DecimalField(max_digits=5, decimal_places=4)
    avg_trade_return = models.DecimalField(max_digits=8, decimal_places=4)
    
    # Sector exposure
    sector_exposures = models.JSONField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Backtest Result"
        verbose_name_plural = "Backtest Results"
    
    def __str__(self):
        return f"Backtest Result for {self.portfolio.name}"
