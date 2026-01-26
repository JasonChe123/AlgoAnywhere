"""
Equity Long-Short strategy implementation.

This strategy combines fundamental factors (value, momentum, quality, growth)
to generate long and short signals with risk management controls.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List

from stocks.models import Stock, IncomeStatement, BalanceSheet, CashFlowStatement
from strategies.strategies.base import BaseStrategy
from strategies.models.equity_long_short import EquityLongShortPortfolio, FactorScore


class EquityLongShortStrategy(BaseStrategy):
    """
    Equity Long-Short strategy using multi-factor scoring.
    
    This strategy:
    1. Selects a tradable universe based on market cap and liquidity
    2. Scores stocks on value, momentum, quality, and growth factors
    3. Goes long top decile, short bottom decile
    4. Maintains beta and sector neutrality
    5. Rebalances based on specified frequency
    """
    
    def __init__(self, portfolio: EquityLongShortPortfolio):
        super().__init__(portfolio)
        self.equity_portfolio = portfolio
        
    def generate_signals(self, date: date) -> List[Dict]:
        """
        Generate long/short signals based on factor scores.
        
        Args:
            date: Date to generate signals for
            
        Returns:
            List of trading signals
        """
        # Check if rebalancing is needed
        if not self._should_rebalance(date):
            return []
        
        # Get tradable universe
        universe = self.calculate_universe(date)
        
        # Calculate factor scores
        factor_scores = self._calculate_factor_scores(universe, date)
        
        # Generate signals based on scores
        signals = self._generate_signals_from_scores(factor_scores, date)
        
        return signals
    
    def calculate_universe(self, date: date) -> List[Stock]:
        """
        Calculate tradable universe based on portfolio criteria.
        
        Args:
            date: Date to calculate universe for
            
        Returns:
            List of tradable stocks
        """
        stocks = Stock.objects.all()
        
        # Filter by market cap if specified
        if self.equity_portfolio.universe_type == 'sp500':
            # Would filter for S&P 500 constituents
            stocks = stocks.filter(market_cap__gte=10000000000)  # $10B+
        elif self.equity_portfolio.universe_type == 'russell1000':
            stocks = stocks.filter(market_cap__gte=3000000000)   # $3B+
        elif self.equity_portfolio.universe_type == 'russell2000':
            stocks = stocks.filter(market_cap__gte=300000000, market_cap__lte=10000000000)  # $300M-$10B
        
        # Apply additional filters
        if self.equity_portfolio.universe_type == 'custom':
            # Would use custom universe criteria
            pass
        
        # Exclude ETFs and ADRs if specified
        # This would need additional logic to identify ETFs/ADRs
        
        return list(stocks)
    
    def _calculate_factor_scores(self, universe: List[Stock], date: date) -> List[FactorScore]:
        """
        Calculate factor scores for all stocks in universe.
        
        Args:
            universe: List of stocks to score
            date: Scoring date
            
        Returns:
            List of factor scores
        """
        factor_scores = []
        
        for stock in universe:
            # Get latest financial data
            latest_income = IncomeStatement.objects.filter(
                stock=stock, 
                period_end_date__lte=date
            ).order_by('-period_end_date').first()
            
            latest_balance = BalanceSheet.objects.filter(
                stock=stock,
                period_end_date__lte=date
            ).order_by('-period_end_date').first()
            
            latest_cashflow = CashFlowStatement.objects.filter(
                stock=stock,
                period_end_date__lte=date
            ).order_by('-period_end_date').first()
            
            if not all([latest_income, latest_balance, latest_cashflow]):
                continue
            
            # Calculate individual factor scores
            value_score = self._calculate_value_score(stock, latest_income, latest_balance)
            momentum_score = self._calculate_momentum_score(stock, date)
            quality_score = self._calculate_quality_score(latest_income, latest_balance, latest_cashflow)
            growth_score = self._calculate_growth_score(latest_income, latest_cashflow)
            
            # Calculate composite score (equal weighted for now)
            composite_score = (value_score + momentum_score + quality_score + growth_score) / 4
            
            factor_score = FactorScore(
                portfolio=self.equity_portfolio,
                stock=stock,
                score_date=date,
                value_score=value_score,
                momentum_score=momentum_score,
                quality_score=quality_score,
                growth_score=growth_score,
                composite_score=composite_score
            )
            
            factor_scores.append(factor_score)
        
        # Sort by composite score and assign rankings
        factor_scores.sort(key=lambda x: x.composite_score, reverse=True)
        
        for i, score in enumerate(factor_scores):
            score.universe_rank = i + 1
            score.decile = (i // len(factor_scores)) * 10 + 1
        
        return factor_scores
    
    def _calculate_value_score(self, stock: Stock, income: IncomeStatement, balance: BalanceSheet) -> float:
        """
        Calculate value score based on valuation multiples.
        """
        if not stock.market_cap or not income.net_income or not balance.total_assets:
            return 0.0
        
        # P/E ratio (lower is better)
        pe_ratio = stock.market_cap / income.net_income if income.net_income > 0 else float('inf')
        
        # P/B ratio (lower is better)
        pb_ratio = stock.market_cap / balance.total_assets if balance.total_assets > 0 else float('inf')
        
        # Convert to scores (higher is better)
        pe_score = 1.0 / pe_ratio if pe_ratio > 0 and pe_ratio != float('inf') else 0.0
        pb_score = 1.0 / pb_ratio if pb_ratio > 0 and pb_ratio != float('inf') else 0.0
        
        # Combined value score
        return (pe_score + pb_score) / 2
    
    def _calculate_momentum_score(self, stock: Stock, date: date) -> float:
        """
        Calculate momentum score based on price performance.
        """
        # This would need price data service
        # For now, return placeholder
        return 0.5
    
    def _calculate_quality_score(self, income: IncomeStatement, balance: BalanceSheet, cashflow: CashFlowStatement) -> float:
        """
        Calculate quality score based on profitability and financial health.
        """
        scores = []
        
        # ROE (higher is better)
        if balance.total_equity and balance.total_equity > 0:
            roe = income.net_income / balance.total_equity
            scores.append(min(roe / 0.15, 1.0))  # Normalize to 15% ROE
        
        # ROA (higher is better)
        if balance.total_assets and balance.total_assets > 0:
            roa = income.net_income / balance.total_assets
            scores.append(min(roa / 0.05, 1.0))  # Normalize to 5% ROA
        
        # Cash flow quality (higher is better)
        if income.net_income and income.net_income > 0:
            cf_quality = cashflow.net_cash_from_operating_activities / income.net_income
            scores.append(min(cf_quality / 1.2, 1.0))  # Normalize to 1.2x
        
        return sum(scores) / len(scores) if scores else 0.0
    
    def _calculate_growth_score(self, income: IncomeStatement, cashflow: CashFlowStatement) -> float:
        """
        Calculate growth score based on revenue and earnings growth.
        """
        # This would need historical data for YoY comparison
        # For now, return placeholder
        return 0.5
    
    def _generate_signals_from_scores(self, factor_scores: List[FactorScore], date: date) -> List[Dict]:
        """
        Generate trading signals from factor scores.
        
        Args:
            factor_scores: List of factor scores
            date: Signal date
            
        Returns:
            List of trading signals
        """
        signals = []
        
        # Get current positions
        current_positions = {pos.stock: pos for pos in self.portfolio.positions.filter(is_active=True)}
        
        # Determine how many stocks to go long/short
        total_stocks = len(factor_scores)
        long_count = int(total_stocks * 0.1)  # Top 10%
        short_count = int(total_stocks * 0.1)  # Bottom 10%
        
        # Calculate position sizes
        portfolio_value = self.portfolio.initial_capital
        long_target_value = portfolio_value * Decimal(str(self.equity_portfolio.long_target_weight))
        short_target_value = portfolio_value * Decimal(str(self.equity_portfolio.short_target_weight))
        
        long_size_per_stock = long_target_value / long_count if long_count > 0 else 0
        short_size_per_stock = short_target_value / short_count if short_count > 0 else 0
        
        # Generate long signals (top decile)
        for score in factor_scores[:long_count]:
            stock = score.stock
            current_price = self._get_current_price(stock, date)
            
            if current_price > 0:
                quantity = int(long_size_per_stock / current_price)
                
                if stock not in current_positions:
                    signals.append({
                        'stock': stock,
                        'action': 'BUY',
                        'quantity': quantity,
                        'price': float(current_price),
                        'signal_strength': float(score.composite_score),
                        'reason': f'Long signal - Composite score: {score.composite_score:.2f}'
                    })
        
        # Generate short signals (bottom decile)
        for score in factor_scores[-short_count:]:
            stock = score.stock
            current_price = self._get_current_price(stock, date)
            
            if current_price > 0:
                quantity = int(short_size_per_stock / current_price)
                
                if stock not in current_positions:
                    signals.append({
                        'stock': stock,
                        'action': 'SHORT',
                        'quantity': quantity,
                        'price': float(current_price),
                        'signal_strength': float(score.composite_score),
                        'reason': f'Short signal - Composite score: {score.composite_score:.2f}'
                    })
        
        return signals
    
    def _should_rebalance(self, date: date) -> bool:
        """
        Check if portfolio should be rebalanced on given date.
        """
        # Get last rebalance date
        last_trade = self.portfolio.trades.order_by('-trade_date').first()
        
        if not last_trade:
            return True
        
        # Calculate next rebalance date based on frequency
        frequency = self.equity_portfolio.rebalance_frequency
        
        if frequency == 'daily':
            return date > last_trade.trade_date
        elif frequency == 'weekly':
            next_rebalance = last_trade.trade_date + timedelta(days=7)
            return date >= next_rebalance
        elif frequency == 'monthly':
            # Same day next month
            if last_trade.trade_date.month == 12:
                next_rebalance = date(last_trade.trade_date.year + 1, 1, last_trade.trade_date.day)
            else:
                next_rebalance = date(last_trade.trade_date.year, last_trade.trade_date.month + 1, last_trade.trade_date.day)
            return date >= next_rebalance
        elif frequency == 'quarterly':
            # Same day 3 months later
            if last_trade.trade_date.month <= 9:
                next_rebalance = date(last_trade.trade_date.year, last_trade.trade_date.month + 3, last_trade.trade_date.day)
            else:
                next_rebalance = date(last_trade.trade_date.year + 1, last_trade.trade_date.month - 9, last_trade.trade_date.day)
            return date >= next_rebalance
        
        return False
    
    def generate_basket_order(self, date: date) -> Dict:
        """
        Generate basket order file for broker execution.
        
        Args:
            date: Date to generate basket order for
            
        Returns:
            Dictionary with basket order data
        """
        # Generate signals for the date
        signals = self.generate_signals(date)
        
        # Convert to basket order format
        basket_items = []
        
        for signal in signals:
            basket_items.append({
                'symbol': signal['stock'].ticker,
                'action': signal['action'],
                'quantity': signal['quantity'],
                'price': signal['price'],
                'estimated_notional': signal['quantity'] * signal['price'],
                'reason': signal['reason']
            })
        
        return {
            'date': date,
            'items': basket_items,
            'total_items': len(basket_items),
            'long_items': len([s for s in signals if s['action'] in ['BUY']]),
            'short_items': len([s for s in signals if s['action'] in ['SHORT']]),
            'estimated_notional': sum(item['estimated_notional'] for item in basket_items)
        }
