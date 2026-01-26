"""
Signal generation for equity long-short strategies.

This module provides functions to calculate factor scores and generate
trading signals for equity long-short strategies.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from stocks.models import Stock, IncomeStatement, BalanceSheet, CashFlowStatement
from strategies.models.equity_long_short import FactorScore


class EquitySignalGenerator:
    """
    Generate signals for equity long-short strategies using multi-factor approach.
    """
    
    def __init__(self, lookback_periods: Dict = None):
        """
        Initialize signal generator.
        
        Args:
            lookback_periods: Dictionary of lookback periods for different calculations
        """
        self.lookback_periods = lookback_periods or {
            'momentum': [21, 63, 126, 252],  # Trading days
            'fundamental': 252,  # 1 year
            'quality': 252,
        }
    
    def calculate_value_signals(self, universe: List[Stock], score_date: date) -> Dict[str, float]:
        """
        Calculate value signals based on fundamental multiples.
        
        Args:
            universe: List of stocks to analyze
            score_date: Date for calculations
            
        Returns:
            Dictionary mapping stock ticker to value score
        """
        value_scores = {}
        
        for stock in universe:
            # Get latest financial data
            latest_income = IncomeStatement.objects.filter(
                stock=stock, 
                period_end_date__lte=score_date
            ).order_by('-period_end_date').first()
            
            latest_balance = BalanceSheet.objects.filter(
                stock=stock,
                period_end_date__lte=score_date
            ).order_by('-period_end_date').first()
            
            if not latest_income or not latest_balance:
                continue
            
            # Calculate valuation multiples
            multiples = self._calculate_valuation_multiples(stock, latest_income, latest_balance)
            
            # Convert multiples to z-scores
            value_score = self._multiples_to_score(multiples)
            value_scores[stock.ticker] = value_score
        
        return value_scores
    
    def calculate_momentum_signals(self, universe: List[Stock], score_date: date) -> Dict[str, float]:
        """
        Calculate momentum signals based on price performance.
        
        Args:
            universe: List of stocks to analyze
            score_date: Date for calculations
            
        Returns:
            Dictionary mapping stock ticker to momentum score
        """
        momentum_scores = {}
        
        for stock in universe:
            # Get price data for different periods
            price_data = self._get_price_data(stock, score_date, max(self.lookback_periods['momentum']))
            
            if len(price_data) < max(self.lookback_periods['momentum']):
                continue
            
            # Calculate momentum for different periods
            momentum_values = []
            for period in self.lookback_periods['momentum']:
                if len(price_data) >= period:
                    current_price = price_data[-1]
                    past_price = price_data[-period-1] if period < len(price_data) else price_data[0]
                    momentum = (current_price - past_price) / past_price
                    momentum_values.append(momentum)
            
            # Combine momentum signals (weighted average)
            if momentum_values:
                # More weight to recent periods
                weights = [0.1, 0.2, 0.3, 0.4]  # Increasing weights
                momentum_score = np.average(momentum_values, weights=weights[:len(momentum_values)])
                momentum_scores[stock.ticker] = momentum_score
        
        return momentum_scores
    
    def calculate_quality_signals(self, universe: List[Stock], score_date: date) -> Dict[str, float]:
        """
        Calculate quality signals based on profitability and financial health.
        
        Args:
            universe: List of stocks to analyze
            score_date: Date for calculations
            
        Returns:
            Dictionary mapping stock ticker to quality score
        """
        quality_scores = {}
        
        for stock in universe:
            # Get latest financial data
            latest_income = IncomeStatement.objects.filter(
                stock=stock, 
                period_end_date__lte=score_date
            ).order_by('-period_end_date').first()
            
            latest_balance = BalanceSheet.objects.filter(
                stock=stock,
                period_end_date__lte=score_date
            ).order_by('-period_end_date').first()
            
            latest_cashflow = CashFlowStatement.objects.filter(
                stock=stock,
                period_end_date__lte=score_date
            ).order_by('-period_end_date').first()
            
            if not all([latest_income, latest_balance, latest_cashflow]):
                continue
            
            # Calculate quality metrics
            quality_metrics = self._calculate_quality_metrics(
                latest_income, latest_balance, latest_cashflow
            )
            
            # Convert metrics to quality score
            quality_score = self._metrics_to_quality_score(quality_metrics)
            quality_scores[stock.ticker] = quality_score
        
        return quality_scores
    
    def calculate_growth_signals(self, universe: List[Stock], score_date: date) -> Dict[str, float]:
        """
        Calculate growth signals based on revenue and earnings growth.
        
        Args:
            universe: List of stocks to analyze
            score_date: Date for calculations
            
        Returns:
            Dictionary mapping stock ticker to growth score
        """
        growth_scores = {}
        
        for stock in universe:
            # Get historical financial data for growth calculation
            income_history = IncomeStatement.objects.filter(
                stock=stock,
                period_end_date__lte=score_date
            ).order_by('-period_end_date')[:8]  # Last 8 quarters
            
            if len(income_history) < 4:  # Need at least 1 year of data
                continue
            
            # Calculate growth rates
            growth_metrics = self._calculate_growth_metrics(income_history)
            
            # Convert to growth score
            growth_score = self._growth_to_score(growth_metrics)
            growth_scores[stock.ticker] = growth_score
        
        return growth_scores
    
    def calculate_composite_signals(self, universe: List[Stock], score_date: date, 
                                  weights: Dict[str, float] = None) -> Dict[str, float]:
        """
        Calculate composite signals combining all factors.
        
        Args:
            universe: List of stocks to analyze
            score_date: Date for calculations
            weights: Weights for different factors
            
        Returns:
            Dictionary mapping stock ticker to composite score
        """
        weights = weights or {
            'value': 0.25,
            'momentum': 0.25,
            'quality': 0.25,
            'growth': 0.25
        }
        
        # Calculate individual factor signals
        value_signals = self.calculate_value_signals(universe, score_date)
        momentum_signals = self.calculate_momentum_signals(universe, score_date)
        quality_signals = self.calculate_quality_signals(universe, score_date)
        growth_signals = self.calculate_growth_signals(universe, score_date)
        
        # Combine into composite score
        composite_scores = {}
        
        for stock in universe:
            ticker = stock.ticker
            scores = []
            factor_weights = []
            
            if ticker in value_signals:
                scores.append(value_signals[ticker])
                factor_weights.append(weights['value'])
            
            if ticker in momentum_signals:
                scores.append(momentum_signals[ticker])
                factor_weights.append(weights['momentum'])
            
            if ticker in quality_signals:
                scores.append(quality_signals[ticker])
                factor_weights.append(weights['quality'])
            
            if ticker in growth_signals:
                scores.append(growth_signals[ticker])
                factor_weights.append(weights['growth'])
            
            if scores:
                # Weighted average of available factors
                total_weight = sum(factor_weights)
                normalized_weights = [w / total_weight for w in factor_weights]
                composite_scores[ticker] = np.average(scores, weights=normalized_weights)
        
        return composite_scores
    
    def _calculate_valuation_multiples(self, stock: Stock, income: IncomeStatement, 
                                     balance: BalanceSheet) -> Dict[str, float]:
        """
        Calculate valuation multiples for a stock.
        """
        multiples = {}
        
        # P/E ratio
        if stock.market_cap and income.net_income and income.net_income > 0:
            multiples['pe'] = float(stock.market_cap / income.net_income)
        
        # P/B ratio
        if stock.market_cap and balance.total_assets and balance.total_assets > 0:
            multiples['pb'] = float(stock.market_cap / balance.total_assets)
        
        # P/S ratio
        if stock.market_cap and income.revenue and income.revenue > 0:
            multiples['ps'] = float(stock.market_cap / income.revenue)
        
        # EV/EBITDA (would need more data)
        # multiples['ev_ebitda'] = self._calculate_ev_ebitda(stock, income, balance)
        
        return multiples
    
    def _multiples_to_score(self, multiples: Dict[str, float]) -> float:
        """
        Convert valuation multiples to a value score.
        Lower multiples = higher value score.
        """
        if not multiples:
            return 0.0
        
        # Invert multiples and normalize
        scores = []
        for multiple in multiples.values():
            if multiple > 0 and multiple < 100:  # Filter out extreme values
                score = 1.0 / multiple
                scores.append(score)
        
        return np.mean(scores) if scores else 0.0
    
    def _calculate_quality_metrics(self, income: IncomeStatement, balance: BalanceSheet, 
                                 cashflow: CashFlowStatement) -> Dict[str, float]:
        """
        Calculate quality metrics for a stock.
        """
        metrics = {}
        
        # ROE
        if balance.total_equity and balance.total_equity > 0:
            metrics['roe'] = float(income.net_income / balance.total_equity)
        
        # ROA
        if balance.total_assets and balance.total_assets > 0:
            metrics['roa'] = float(income.net_income / balance.total_assets)
        
        # Operating margin
        if income.revenue and income.revenue > 0:
            metrics['operating_margin'] = float(income.operating_income / income.revenue)
        
        # Cash flow quality
        if income.net_income and income.net_income > 0:
            metrics['cf_quality'] = float(cashflow.net_cash_from_operating_activities / income.net_income)
        
        return metrics
    
    def _metrics_to_quality_score(self, metrics: Dict[str, float]) -> float:
        """
        Convert quality metrics to a quality score.
        Higher metrics = higher quality score.
        """
        if not metrics:
            return 0.0
        
        # Normalize metrics to 0-1 scale
        normalized_scores = []
        
        # ROE (normalize to 15%)
        if 'roe' in metrics:
            normalized_scores.append(min(metrics['roe'] / 0.15, 1.0))
        
        # ROA (normalize to 5%)
        if 'roa' in metrics:
            normalized_scores.append(min(metrics['roa'] / 0.05, 1.0))
        
        # Operating margin (normalize to 15%)
        if 'operating_margin' in metrics:
            normalized_scores.append(min(metrics['operating_margin'] / 0.15, 1.0))
        
        # Cash flow quality (normalize to 1.2x)
        if 'cf_quality' in metrics:
            normalized_scores.append(min(metrics['cf_quality'] / 1.2, 1.0))
        
        return np.mean(normalized_scores) if normalized_scores else 0.0
    
    def _calculate_growth_metrics(self, income_history: List[IncomeStatement]) -> Dict[str, float]:
        """
        Calculate growth metrics from historical data.
        """
        if len(income_history) < 4:
            return {}
        
        # Extract revenue and earnings
        revenues = [float(income.revenue) for income in income_history if income.revenue]
        earnings = [float(income.net_income) for income in income_history if income.net_income]
        
        growth_metrics = {}
        
        # Revenue growth (YoY)
        if len(revenues) >= 4:
            recent_revenue = revenues[0]
            past_revenue = revenues[4] if len(revenues) > 4 else revenues[-1]
            if past_revenue > 0:
                growth_metrics['revenue_growth'] = (recent_revenue - past_revenue) / past_revenue
        
        # Earnings growth (YoY)
        if len(earnings) >= 4:
            recent_earnings = earnings[0]
            past_earnings = earnings[4] if len(earnings) > 4 else earnings[-1]
            if past_earnings > 0:
                growth_metrics['earnings_growth'] = (recent_earnings - past_earnings) / past_earnings
        
        return growth_metrics
    
    def _growth_to_score(self, growth_metrics: Dict[str, float]) -> float:
        """
        Convert growth metrics to a growth score.
        """
        if not growth_metrics:
            return 0.0
        
        scores = []
        
        # Revenue growth (normalize to 20%)
        if 'revenue_growth' in growth_metrics:
            scores.append(min(growth_metrics['revenue_growth'] / 0.20, 1.0))
        
        # Earnings growth (normalize to 20%)
        if 'earnings_growth' in growth_metrics:
            scores.append(min(growth_metrics['earnings_growth'] / 0.20, 1.0))
        
        return np.mean(scores) if scores else 0.0
    
    def _get_price_data(self, stock: Stock, end_date: date, days: int) -> List[float]:
        """
        Get historical price data for a stock.
        This would integrate with a price data service.
        """
        # Placeholder implementation
        # Would integrate with price data service like Alpha Vantage, Yahoo Finance, etc.
        return [100.0] * days  # Placeholder
    
    def rank_stocks_by_signals(self, signals: Dict[str, float]) -> List[Tuple[str, float, int]]:
        """
        Rank stocks by signal scores.
        
        Args:
            signals: Dictionary mapping ticker to signal score
            
        Returns:
            List of (ticker, score, rank) tuples
        """
        # Sort by score (descending)
        sorted_stocks = sorted(signals.items(), key=lambda x: x[1], reverse=True)
        
        # Add rankings
        ranked_stocks = []
        for i, (ticker, score) in enumerate(sorted_stocks):
            ranked_stocks.append((ticker, score, i + 1))
        
        return ranked_stocks
