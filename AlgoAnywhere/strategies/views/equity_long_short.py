"""
Views for equity long-short strategy backtesting interface.

This module provides web interface for running backtests, viewing results,
and generating basket orders for broker execution.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.paginator import Paginator
from datetime import date, timedelta
import csv
import json

from stocks.models import Stock
from strategies.models.equity_long_short import (
    EquityLongShortPortfolio, EquityUniverse, BasketOrder, BacktestResult
)
from strategies.strategies.equity_long_short import EquityLongShortStrategy
from strategies.signals.equity_long_short import EquitySignalGenerator


@login_required
def equity_long_short_home(request):
    """
    Home page for equity long-short strategy.
    """
    # Get user's portfolios
    portfolios = EquityLongShortPortfolio.objects.filter(user=request.user).order_by('-created_at')
    
    # Get recent backtests
    recent_backtests = portfolios[:5]
    
    context = {
        'portfolios': portfolios,
        'recent_backtests': recent_backtests,
    }
    
    return render(request, 'strategies/equity_long_short/home.html', context)


@login_required
def create_portfolio(request):
    """
    Create a new equity long-short portfolio.
    """
    if request.method == 'POST':
        # Extract form data
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        initial_capital = float(request.POST.get('initial_capital', 1000000))
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        
        # Strategy parameters
        universe_type = request.POST.get('universe_type', 'sp500')
        long_target_weight = float(request.POST.get('long_target_weight', 0.5))
        short_target_weight = float(request.POST.get('short_target_weight', 0.5))
        max_position_weight = float(request.POST.get('max_position_weight', 0.05))
        rebalance_frequency = request.POST.get('rebalance_frequency', 'monthly')
        beta_neutral = request.POST.get('beta_neutral') == 'on'
        sector_neutral = request.POST.get('sector_neutral') == 'on'
        max_leverage = float(request.POST.get('max_leverage', 2.0))
        
        # Create portfolio
        portfolio = EquityLongShortPortfolio.objects.create(
            name=name,
            description=description,
            user=request.user,
            strategy_type='equity_long_short',
            initial_capital=initial_capital,
            start_date=start_date,
            end_date=end_date if end_date else None,
            universe_type=universe_type,
            long_target_weight=long_target_weight,
            short_target_weight=short_target_weight,
            max_position_weight=max_position_weight,
            rebalance_frequency=rebalance_frequency,
            beta_neutral=beta_neutral,
            sector_neutral=sector_neutral,
            max_leverage=max_leverage
        )
        
        return redirect('strategies:equity_long_short_backtest', portfolio_id=portfolio.id)
    
    return render(request, 'strategies/equity_long_short/create_portfolio.html')


@login_required
def backtest_strategy(request, portfolio_id):
    """
    Run backtest for equity long-short strategy.
    """
    portfolio = EquityLongShortPortfolio.objects.get(id=portfolio_id, user=request.user)
    
    if request.method == 'POST':
        # Get backtest parameters
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        
        # Run backtest
        strategy = EquityLongShortStrategy(portfolio)
        
        start_date_obj = timezone.datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date_obj = timezone.datetime.strptime(end_date, '%Y-%m-%d').date()
        
        try:
            results = strategy.run_backtest(start_date_obj, end_date_obj)
            
            # Save backtest results
            BacktestResult.objects.update_or_create(
                portfolio=portfolio,
                defaults={
                    'total_return': results['total_return'],
                    'annualized_return': results['annualized_return'],
                    'sharpe_ratio': results['sharpe_ratio'],
                    'max_drawdown': results['max_drawdown'],
                    'volatility': results['volatility'],
                    'total_trades': len(results.get('trades', [])),
                    'win_rate': 0.0,  # Would calculate from trades
                    'avg_trade_return': 0.0,  # Would calculate from trades
                }
            )
            
            return JsonResponse({
                'success': True,
                'results': results
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    # Get portfolio parameters for display
    context = {
        'portfolio': portfolio,
    }
    
    return render(request, 'strategies/equity_long_short/backtest.html', context)


@login_required
def portfolio_results(request, portfolio_id):
    """
    Display backtest results for a portfolio.
    """
    portfolio = EquityLongShortPortfolio.objects.get(id=portfolio_id, user=request.user)
    
    try:
        results = portfolio.backtest_result
    except BacktestResult.DoesNotExist:
        results = None
    
    # Get portfolio snapshots for chart data
    snapshots = portfolio.snapshots.order_by('date')
    
    # Get recent trades
    trades = portfolio.trades.order_by('-trade_date')[:20]
    
    # Get current positions
    positions = portfolio.positions.filter(is_active=True)
    
    context = {
        'portfolio': portfolio,
        'results': results,
        'snapshots': snapshots,
        'trades': trades,
        'positions': positions,
    }
    
    return render(request, 'strategies/equity_long_short/results.html', context)


@login_required
def generate_basket_order(request, portfolio_id):
    """
    Generate basket order for current signals.
    """
    portfolio = EquityLongShortPortfolio.objects.get(id=portfolio_id, user=request.user)
    
    if request.method == 'POST':
        order_date = request.POST.get('order_date')
        
        try:
            order_date_obj = timezone.datetime.strptime(order_date, '%Y-%m-%d').date()
            
            # Generate basket order
            strategy = EquityLongShortStrategy(portfolio)
            basket_data = strategy.generate_basket_order(order_date_obj)
            
            # Create basket order record
            basket_order = BasketOrder.objects.create(
                portfolio=portfolio,
                order_date=order_date_obj,
                total_orders=basket_data['total_items'],
                long_orders=basket_data['long_items'],
                short_orders=basket_data['short_items'],
                estimated_notional=basket_data['estimated_notional']
            )
            
            # Create basket order items
            from strategies.models.equity_long_short import BasketOrderItem
            
            for item_data in basket_data['items']:
                stock = Stock.objects.get(ticker=item_data['symbol'])
                
                BasketOrderItem.objects.create(
                    basket_order=basket_order,
                    stock=stock,
                    action=item_data['action'],
                    quantity=item_data['quantity'],
                    target_weight=item_data['quantity'] * item_data['price'] / portfolio.initial_capital,
                    last_price=item_data['price'],
                    estimated_notional=item_data['estimated_notional'],
                    signal_reason=item_data['reason']
                )
            
            return JsonResponse({
                'success': True,
                'basket_order_id': basket_order.id,
                'data': basket_data
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    # Default to today
    today = timezone.now().date()
    
    context = {
        'portfolio': portfolio,
        'today': today,
    }
    
    return render(request, 'strategies/equity_long_short/generate_basket.html', context)


@login_required
def basket_order_detail(request, basket_order_id):
    """
    Display details of a generated basket order.
    """
    basket_order = BasketOrder.objects.get(id=basket_order_id, portfolio__user=request.user)
    items = basket_order.items.all()
    
    context = {
        'basket_order': basket_order,
        'items': items,
    }
    
    return render(request, 'strategies/equity_long_short/basket_detail.html', context)


@login_required
def download_basket_order(request, basket_order_id, format_type):
    """
    Download basket order in CSV or Excel format.
    """
    basket_order = BasketOrder.objects.get(id=basket_order_id, portfolio__user=request.user)
    items = basket_order.items.all()
    
    if format_type == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="basket_order_{basket_order.order_date}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Symbol', 'Action', 'Quantity', 'Price', 'Notional', 'Reason'])
        
        for item in items:
            writer.writerow([
                item.stock.ticker,
                item.action,
                item.quantity,
                item.last_price,
                item.estimated_notional,
                item.signal_reason
            ])
        
        return response
    
    elif format_type == 'excel':
        # Would use pandas/openpyxl for Excel export
        # For now, return CSV
        return download_basket_order(request, basket_order_id, 'csv')
    
    return redirect('strategies:basket_order_detail', basket_order_id=basket_order_id)


@login_required
def manage_universes(request):
    """
    Manage custom stock universes.
    """
    universes = EquityUniverse.objects.filter(user=request.user).order_by('name')
    
    if request.method == 'POST':
        # Create new universe
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        stock_tickers = request.POST.get('stock_tickers', '').split('\n')
        
        # Create universe
        universe = EquityUniverse.objects.create(
            name=name,
            description=description,
            user=request.user
        )
        
        # Add stocks to universe
        for ticker in stock_tickers:
            ticker = ticker.strip()
            if ticker:
                try:
                    stock = Stock.objects.get(ticker=ticker)
                    universe.stocks.add(stock)
                except Stock.DoesNotExist:
                    continue
        
        return redirect('strategies:manage_universes')
    
    context = {
        'universes': universes,
    }
    
    return render(request, 'strategies/equity_long_short/manage_universes.html', context)


@login_required
def api_portfolio_performance(request, portfolio_id):
    """
    API endpoint to get portfolio performance data for charts.
    """
    portfolio = EquityLongShortPortfolio.objects.get(id=portfolio_id, user=request.user)
    
    # Get snapshots data
    snapshots = portfolio.snapshots.order_by('date')
    
    data = {
        'dates': [snapshot.date.strftime('%Y-%m-%d') for snapshot in snapshots],
        'total_values': [float(snapshot.total_value) for snapshot in snapshots],
        'daily_returns': [float(snapshot.daily_return) if snapshot.daily_return else 0 for snapshot in snapshots],
        'cumulative_returns': [float(snapshot.cumulative_return) if snapshot.cumulative_return else 0 for snapshot in snapshots],
    }
    
    return JsonResponse(data)


@login_required
def api_current_signals(request, portfolio_id):
    """
    API endpoint to get current signals for a portfolio.
    """
    portfolio = EquityLongShortPortfolio.objects.get(id=portfolio_id, user=request.user)
    
    # Generate current signals
    signal_date = date.today()
    strategy = EquityLongShortStrategy(portfolio)
    
    try:
        signals = strategy.generate_signals(signal_date)
        
        data = {
            'date': signal_date.strftime('%Y-%m-%d'),
            'signals': [
                {
                    'symbol': signal['stock'].ticker,
                    'action': signal['action'],
                    'quantity': signal['quantity'],
                    'price': signal['price'],
                    'signal_strength': signal.get('signal_strength', 0),
                    'reason': signal.get('reason', '')
                }
                for signal in signals
            ]
        }
        
        return JsonResponse(data)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
