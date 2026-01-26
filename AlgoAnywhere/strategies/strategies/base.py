"""
Base strategy class for all trading strategies.

This provides the foundation for implementing trading strategies with
common functionality for backtesting, signal generation, and performance tracking.
"""

from abc import ABC, abstractmethod
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.db import transaction
from stocks.models import Stock
from strategies.models.base import Portfolio, Position, Trade, PortfolioSnapshot


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    This class defines the interface that all strategies must implement
    and provides common functionality for backtesting and execution.
    """
    
    def __init__(self, portfolio: Portfolio):
        self.portfolio = portfolio
        self.positions = {}
        self.cash = Decimal(str(portfolio.initial_capital))
        self.current_date = None
        
    @abstractmethod
    def generate_signals(self, date: date) -> List[Dict]:
        """
        Generate trading signals for a given date.
        
        Args:
            date: The date to generate signals for
            
        Returns:
            List of signal dictionaries with keys: stock, action, quantity, price, reason
        """
        pass
    
    @abstractmethod
    def calculate_universe(self, date: date) -> List[Stock]:
        """
        Calculate the tradable universe for a given date.
        
        Args:
            date: The date to calculate universe for
            
        Returns:
            List of stocks in the tradable universe
        """
        pass
    
    def execute_trades(self, signals: List[Dict], date: date) -> None:
        """
        Execute trading signals and update positions.
        
        Args:
            signals: List of trading signals
            date: Execution date
        """
        with transaction.atomic():
            for signal in signals:
                self._execute_single_trade(signal, date)
    
    def _execute_single_trade(self, signal: Dict, date: date) -> None:
        """
        Execute a single trading signal.
        
        Args:
            signal: Trading signal dictionary
            date: Execution date
        """
        stock = signal['stock']
        action = signal['action']
        quantity = signal['quantity']
        price = Decimal(str(signal['price']))
        
        # Calculate trade cost
        trade_cost = quantity * price
        
        # Update cash based on action
        if action in ['BUY', 'SHORT']:
            self.cash -= trade_cost
        else:  # SELL, COVER
            self.cash += trade_cost
        
        # Update position
        current_position = self.positions.get(stock, 0)
        
        if action == 'BUY':
            self.positions[stock] = current_position + quantity
        elif action == 'SELL':
            self.positions[stock] = current_position - quantity
        elif action == 'SHORT':
            self.positions[stock] = current_position - quantity
        elif action == 'COVER':
            self.positions[stock] = current_position + quantity
        
        # Create trade record
        Trade.objects.create(
            portfolio=self.portfolio,
            stock=stock,
            trade_type=action,
            quantity=quantity,
            price=price,
            trade_date=date,
            signal_strength=signal.get('signal_strength'),
            strategy_reason=signal.get('reason', '')
        )
    
    def update_positions(self, date: date) -> None:
        """
        Update position values based on current prices.
        
        Args:
            date: Date to update positions for
        """
        total_value = self.cash
        long_value = Decimal('0')
        short_value = Decimal('0')
        
        for stock, quantity in self.positions.items():
            if quantity == 0:
                continue
                
            # Get current price (this would need price data service)
            current_price = self._get_current_price(stock, date)
            position_value = quantity * current_price
            
            if quantity > 0:
                long_value += position_value
            else:
                short_value += abs(position_value)
            
            total_value += position_value
        
        # Create portfolio snapshot
        PortfolioSnapshot.objects.update_or_create(
            portfolio=self.portfolio,
            date=date,
            defaults={
                'total_value': total_value,
                'cash_balance': self.cash,
                'long_value': long_value,
                'short_value': short_value
            }
        )
    
    def _get_current_price(self, stock: Stock, date: date) -> Decimal:
        """
        Get current price for a stock on a given date.
        This would need to be implemented with price data service.
        
        Args:
            stock: Stock to get price for
            date: Date to get price for
            
        Returns:
            Current price
        """
        # Placeholder - would integrate with price data service
        return Decimal('100.00')
    
    def calculate_performance_metrics(self) -> Dict:
        """
        Calculate performance metrics for the strategy.
        
        Returns:
            Dictionary of performance metrics
        """
        snapshots = list(self.portfolio.snapshots.order_by('date'))
        
        if len(snapshots) < 2:
            return {}
        
        # Calculate returns
        initial_value = snapshots[0].total_value
        final_value = snapshots[-1].total_value
        
        total_return = (final_value - initial_value) / initial_value
        
        # Calculate daily returns
        daily_returns = []
        for i in range(1, len(snapshots)):
            prev_value = snapshots[i-1].total_value
            curr_value = snapshots[i].total_value
            daily_return = (curr_value - prev_value) / prev_value
            daily_returns.append(daily_return)
        
        # Calculate metrics
        if daily_returns:
            import numpy as np
            
            annualized_return = (1 + total_return) ** (252 / len(daily_returns)) - 1
            volatility = np.std(daily_returns) * np.sqrt(252)
            sharpe_ratio = annualized_return / volatility if volatility > 0 else 0
            
            # Calculate maximum drawdown
            running_max = [snapshots[0].total_value]
            drawdowns = []
            
            for snapshot in snapshots[1:]:
                running_max.append(max(running_max[-1], snapshot.total_value))
                drawdown = (snapshot.total_value - running_max[-1]) / running_max[-1]
                drawdowns.append(drawdown)
            
            max_drawdown = min(drawdowns) if drawdowns else 0
        else:
            annualized_return = 0
            volatility = 0
            sharpe_ratio = 0
            max_drawdown = 0
        
        return {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown
        }
    
    def run_backtest(self, start_date: date, end_date: date) -> Dict:
        """
        Run a backtest for the strategy.
        
        Args:
            start_date: Backtest start date
            end_date: Backtest end date
            
        Returns:
            Dictionary with backtest results
        """
        self.current_date = start_date
        results = {
            'start_date': start_date,
            'end_date': end_date,
            'trades': [],
            'snapshots': []
        }
        
        # Initialize portfolio
        self.cash = Decimal(str(self.portfolio.initial_capital))
        self.positions = {}
        
        # Run backtest day by day
        current_date = start_date
        while current_date <= end_date:
            # Generate and execute signals
            signals = self.generate_signals(current_date)
            if signals:
                self.execute_trades(signals, current_date)
                results['trades'].extend(signals)
            
            # Update positions
            self.update_positions(current_date)
            
            # Move to next day
            current_date += timedelta(days=1)
        
        # Calculate final performance metrics
        performance = self.calculate_performance_metrics()
        results.update(performance)
        
        return results
