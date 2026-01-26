"""
Base models for strategies app.

These models provide the foundation for all trading strategies including
portfolios, positions, trades, and performance tracking.
"""

from django.db import models
from django.contrib.auth.models import User
from stocks.models import Stock


class Portfolio(models.Model):
    """
    A portfolio represents a collection of strategy backtests or live trading results.
    Each portfolio can contain multiple positions and tracks overall performance.
    """
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    strategy_type = models.CharField(max_length=50)  # 'equity_long_short', 'momentum', etc.
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    is_backtest = models.BooleanField(default=True)  # True for backtest, False for live trading
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Portfolio parameters
    initial_capital = models.DecimalField(max_digits=15, decimal_places=2, default=1000000)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    
    # Performance metrics
    total_return = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    annualized_return = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    sharpe_ratio = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    max_drawdown = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    volatility = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({'Backtest' if self.is_backtest else 'Live'})"


class Position(models.Model):
    """
    A position represents a holding in a specific stock within a portfolio.
    Can be long (positive quantity) or short (negative quantity).
    """
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='positions')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    quantity = models.IntegerField()  # Positive for long, negative for short
    entry_price = models.DecimalField(max_digits=10, decimal_places=4)
    current_price = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    entry_date = models.DateField()
    exit_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    # Position metrics
    market_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    unrealized_pnl = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    realized_pnl = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    class Meta:
        unique_together = ['portfolio', 'stock', 'entry_date']
        ordering = ['-entry_date']
    
    def __str__(self):
        direction = "LONG" if self.quantity > 0 else "SHORT"
        return f"{direction} {abs(self.quantity)} {self.stock.ticker} @ {self.entry_price}"


class Trade(models.Model):
    """
    A trade represents an individual transaction that creates or modifies a position.
    """
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='trades')
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    trade_type = models.CharField(max_length=10)  # 'BUY', 'SELL', 'SHORT', 'COVER'
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=4)
    trade_date = models.DateField()
    commission = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    
    # Trade metadata
    signal_strength = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    strategy_reason = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-trade_date']
    
    def __str__(self):
        return f"{self.trade_type} {abs(self.quantity)} {self.stock.ticker} @ {self.price}"


class PortfolioSnapshot(models.Model):
    """
    Daily snapshot of portfolio value and metrics for performance tracking.
    """
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='snapshots')
    date = models.DateField()
    total_value = models.DecimalField(max_digits=15, decimal_places=2)
    cash_balance = models.DecimalField(max_digits=15, decimal_places=2)
    long_value = models.DecimalField(max_digits=15, decimal_places=2)
    short_value = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Daily metrics
    daily_return = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    cumulative_return = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    
    class Meta:
        unique_together = ['portfolio', 'date']
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.portfolio.name} - {self.date}: ${self.total_value:,.2f}"


class StrategyParameter(models.Model):
    """
    Store strategy parameters for backtesting and optimization.
    """
    portfolio = models.OneToOneField(Portfolio, on_delete=models.CASCADE, related_name='parameters')
    parameters = models.JSONField()  # Store strategy-specific parameters
    
    def __str__(self):
        return f"Parameters for {self.portfolio.name}"
