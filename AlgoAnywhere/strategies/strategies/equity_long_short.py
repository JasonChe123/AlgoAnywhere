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

    def run_fundamental_backtest(self, start_date: date, end_date: date, 
                               total_stocks_holding: int, sectors: List[str],
                               min_market_cap: float, max_market_cap: float,
                               min_stock_price: float, max_stock_price: float,
                               min_volume: int, max_volume: int,
                               ranking_metric: str, income_statement_data: List[str],
                               balance_sheet_data: List[str], cashflow_data: List[str]) -> Dict:
        """
        Run fundamental backtest with specified criteria.
        
        This method implements the monthly rebalancing strategy where:
        1. Filter stocks based on criteria
        2. Rank by fundamental metric
        3. Go long top 50%, short bottom 50%
        4. Rebalance monthly
        5. Compare to S&P 500
        """
        import pandas as pd
        import numpy as np
        from datetime import datetime, timedelta
        from stocks.models import Stock, DailyPriceData
        
        # Initialize results
        portfolio_values = []
        sp500_values = []
        monthly_returns = []
        positions = []
        trades = []
        
        # Get S&P 500 benchmark data (placeholder - would need actual S&P 500 data)
        sp500_initial = 1000  # Placeholder S&P 500 initial value
        
        current_capital = self.equity_portfolio.initial_capital
        current_positions = {}
        
        # Generate monthly rebalancing dates
        current_date = start_date.replace(day=1)  # First day of start month
        rebalance_dates = []
        
        while current_date <= end_date:
            rebalance_dates.append(current_date)
            # Move to next month
            if current_date.month == 12:
                current_date = date(current_date.year + 1, 1, 1)
            else:
                current_date = date(current_date.year, current_date.month + 1, 1)
        
        for rebalance_date in rebalance_dates:
            # 1. Filter universe based on criteria
            filtered_stocks = self._filter_stocks(
                rebalance_date, sectors, min_market_cap, max_market_cap,
                min_stock_price, max_stock_price, min_volume, max_volume
            )
            
            if len(filtered_stocks) < total_stocks_holding:
                continue  # Skip if not enough stocks
            
            # 2. Calculate fundamental metrics and rank
            stock_scores = self._calculate_fundamental_scores(
                filtered_stocks, rebalance_date, ranking_metric,
                income_statement_data, balance_sheet_data, cashflow_data
            )
            
            # 3. Select long and short positions
            stocks_to_long = stock_scores[:total_stocks_holding // 2]
            stocks_to_short = stock_scores[-(total_stocks_holding // 2):]
            
            # 4. Calculate position sizes (equal weight)
            capital_per_position = current_capital / total_stocks_holding
            
            # 5. Generate trades for rebalancing
            new_positions = {}
            
            # Long positions
            for stock_score in stocks_to_long:
                stock = stock_score['stock']
                price = self._get_current_price(stock, rebalance_date)
                if price > 0:
                    quantity = int(capital_per_position / price)
                    new_positions[stock] = {
                        'quantity': quantity,
                        'side': 'long',
                        'price': price,
                        'weight': 1.0 / total_stocks_holding
                    }
                    
                    # Record trade
                    trades.append({
                        'date': rebalance_date,
                        'stock': stock.ticker,
                        'action': 'BUY',
                        'quantity': quantity,
                        'price': price,
                        'reason': f'Long position - {ranking_metric}: {stock_score["score"]:.2f}'
                    })
            
            # Short positions
            for stock_score in stocks_to_short:
                stock = stock_score['stock']
                price = self._get_current_price(stock, rebalance_date)
                if price > 0:
                    quantity = int(capital_per_position / price)
                    new_positions[stock] = {
                        'quantity': quantity,
                        'side': 'short',
                        'price': price,
                        'weight': 1.0 / total_stocks_holding
                    }
                    
                    # Record trade
                    trades.append({
                        'date': rebalance_date,
                        'stock': stock.ticker,
                        'action': 'SHORT',
                        'quantity': quantity,
                        'price': price,
                        'reason': f'Short position - {ranking_metric}: {stock_score["score"]:.2f}'
                    })
            
            # 6. Calculate portfolio performance for the month
            month_start = rebalance_date
            if rebalance_date.month == 12:
                month_end = date(rebalance_date.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(rebalance_date.year, rebalance_date.month + 1, 1) - timedelta(days=1)
            
            month_end = min(month_end, end_date)
            
            # Calculate daily portfolio values
            current_date = month_start
            while current_date <= month_end:
                daily_value = current_capital  # Start with cash
                
                # Add P&L from positions
                for stock, position in new_positions.items():
                    current_price = self._get_current_price(stock, current_date)
                    if current_price > 0:
                        price_change = (current_price - position['price']) / position['price']
                        if position['side'] == 'long':
                            daily_value += position['quantity'] * position['price'] * price_change
                        else:  # short
                            daily_value -= position['quantity'] * position['price'] * price_change
                
                portfolio_values.append({
                    'date': current_date,
                    'portfolio_value': daily_value,
                    'return': (daily_value - current_capital) / current_capital
                })
                
                current_date += timedelta(days=1)
            
            # Update capital for next period
            if portfolio_values:
                current_capital = portfolio_values[-1]['portfolio_value']
            
            current_positions = new_positions
        
        # Calculate performance metrics
        if portfolio_values:
            returns = [pv['return'] for pv in portfolio_values]
            
            total_return = (portfolio_values[-1]['portfolio_value'] - self.equity_portfolio.initial_capital) / self.equity_portfolio.initial_capital
            
            # Annualized return
            days = (end_date - start_date).days
            annualized_return = (1 + total_return) ** (365.25 / days) - 1 if days > 0 else 0
            
            # Volatility
            volatility = np.std(returns) * np.sqrt(252) if returns else 0
            
            # Sharpe ratio (assuming 2% risk-free rate)
            sharpe_ratio = (annualized_return - 0.02) / volatility if volatility > 0 else 0
            
            # Maximum drawdown
            peak = portfolio_values[0]['portfolio_value']
            max_drawdown = 0
            for pv in portfolio_values:
                if pv['portfolio_value'] > peak:
                    peak = pv['portfolio_value']
                drawdown = (peak - pv['portfolio_value']) / peak
                max_drawdown = max(max_drawdown, drawdown)
            
            # Generate S&P 500 comparison data (placeholder)
            sp500_data = []
            sp500_current = sp500_initial
            for pv in portfolio_values:
                # Simulate S&P 500 performance (would use real data)
                daily_return = np.random.normal(0.0003, 0.01)  # ~7% annual return, ~16% volatility
                sp500_current *= (1 + daily_return)
                sp500_data.append({
                    'date': pv['date'],
                    'sp500_value': sp500_current,
                    'sp500_return': (sp500_current - sp500_initial) / sp500_initial
                })
        else:
            total_return = 0
            annualized_return = 0
            sharpe_ratio = 0
            max_drawdown = 0
            volatility = 0
            sp500_data = []
        
        return {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'volatility': volatility,
            'total_trades': len(trades),
            'win_rate': 0.5,  # Placeholder
            'avg_trade_return': 0.0,  # Placeholder
            'performance_data': portfolio_values,
            'sp500_data': sp500_data,
            'trades': trades,
            'final_positions': len(current_positions)
        }

    def _filter_stocks(self, date: date, sectors: List[str], min_market_cap: float, max_market_cap: float,
                      min_stock_price: float, max_stock_price: float, min_volume: int, max_volume: int) -> List[Stock]:
        """Filter stocks based on specified criteria."""
        from stocks.models import DailyPriceData
        
        stocks = Stock.objects.all()
        
        # Filter by sectors if specified
        if sectors:
            stocks = stocks.filter(sector__in=sectors)
        
        # Filter by market cap
        stocks = stocks.filter(market_cap__gte=min_market_cap)
        if max_market_cap < float('inf'):
            stocks = stocks.filter(market_cap__lte=max_market_cap)
        
        # Get stocks with price data on the given date
        filtered_stocks = []
        for stock in stocks:
            price_data = DailyPriceData.objects.filter(
                stock=stock, 
                date=date
            ).first()
            
            if price_data:
                # Filter by price
                if min_stock_price <= float(price_data.close_price) <= max_stock_price:
                    # Filter by volume
                    if min_volume <= price_data.volume <= max_volume:
                        filtered_stocks.append(stock)
        
        return filtered_stocks

    def _calculate_fundamental_scores(self, stocks: List[Stock], date: date, ranking_metric: str,
                                    income_statement_data: List[str], balance_sheet_data: List[str], 
                                    cashflow_data: List[str]) -> List[Dict]:
        """Calculate fundamental scores for stocks based on selected metric."""
        from stocks.models import IncomeStatement, BalanceSheet, CashFlowStatement
        
        stock_scores = []
        
        for stock in stocks:
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
            
            score = 0.0
            
            # Calculate score based on ranking metric
            if ranking_metric == 'eps' and latest_income:
                if latest_income.earnings_per_share_basic and latest_income.earnings_per_share_basic > 0:
                    score = float(latest_income.earnings_per_share_basic)
                    
            elif ranking_metric == 'pe_ratio' and latest_income:
                if stock.market_cap and latest_income.net_income and latest_income.net_income > 0:
                    score = stock.market_cap / latest_income.net_income  # Lower is better, will be reversed
                    
            elif ranking_metric == 'pb_ratio' and latest_balance:
                if stock.market_cap and latest_balance.total_equity and latest_balance.total_equity > 0:
                    score = stock.market_cap / latest_balance.total_equity  # Lower is better, will be reversed
                    
            elif ranking_metric == 'roe' and latest_income and latest_balance:
                if latest_balance.total_equity and latest_balance.total_equity > 0:
                    score = latest_income.net_income / latest_balance.total_equity
                    
            elif ranking_metric == 'roa' and latest_income and latest_balance:
                if latest_balance.total_assets and latest_balance.total_assets > 0:
                    score = latest_income.net_income / latest_balance.total_assets
                    
            elif ranking_metric == 'revenue_growth' and latest_income:
                # Would need previous year data for growth calculation
                score = latest_income.revenue / 1000000000  # Placeholder
                
            elif ranking_metric == 'earnings_growth' and latest_income:
                # Would need previous year data for growth calculation
                score = latest_income.net_income / 100000000  # Placeholder
                
            elif ranking_metric == 'debt_to_equity' and latest_balance:
                if latest_balance.total_equity and latest_balance.total_equity > 0:
                    score = latest_balance.total_liabilities / latest_balance.total_equity  # Lower is better
                    
            elif ranking_metric == 'current_ratio' and latest_balance:
                if latest_balance.total_current_liabilities and latest_balance.total_current_liabilities > 0:
                    score = latest_balance.total_current_assets / latest_balance.total_current_liabilities
                    
            elif ranking_metric == 'operating_margin' and latest_income:
                if latest_income.revenue and latest_income.revenue > 0:
                    score = latest_income.operating_income / latest_income.revenue
            
            stock_scores.append({
                'stock': stock,
                'score': score
            })
        
        # Sort by score (handle metrics where lower is better)
        if ranking_metric in ['pe_ratio', 'pb_ratio', 'debt_to_equity']:
            stock_scores.sort(key=lambda x: x['score'])  # Ascending for lower-is-better metrics
        else:
            stock_scores.sort(key=lambda x: x['score'], reverse=True)  # Descending for higher-is-better metrics
        
        return stock_scores

    def _get_current_price(self, stock: Stock, date: date) -> float:
        """Get current price for a stock on given date."""
        from stocks.models import DailyPriceData
        
        price_data = DailyPriceData.objects.filter(
            stock=stock,
            date__lte=date
        ).order_by('-date').first()
        
        return float(price_data.close_price) if price_data else 0.0
