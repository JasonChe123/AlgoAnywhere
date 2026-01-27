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
def backtest_config(request):
    """
    Display backtest configuration page with fundamental data criteria.
    """
    from stocks.models import Stock
    
    # Get unique sectors with stock counts for filtering
    sectors_data = []
    sectors = Stock.objects.values_list('sector', flat=True).distinct().exclude(sector__isnull=True).exclude(sector='').order_by('sector')
    
    for sector in sectors:
        stock_count = Stock.objects.filter(sector=sector).count()
        sectors_data.append({'id': sector, 'name': sector, 'stock_count': stock_count})
    
    if request.method == 'POST':
        # Extract backtest parameters
        backtest_data = {
            'name': request.POST.get('name'),
            'start_date': request.POST.get('start_date'),
            'end_date': request.POST.get('end_date'),
            'total_stocks_holding': int(request.POST.get('total_stocks_holding', 20)),
            
            # Filtering criteria
            'sectors': request.POST.getlist('sectors'),
            'min_market_cap': float(request.POST.get('min_market_cap', 0.1)) * 1000000000,  # Convert B to actual
            'max_market_cap': float(request.POST.get('max_market_cap', 1000)) * 1000000000,  # Convert B to actual
            'min_stock_price': float(request.POST.get('min_stock_price', 0)),
            'max_stock_price': float(request.POST.get('max_stock_price', float('inf'))),
            'min_volume': int(request.POST.get('min_volume', 0)),
            'max_volume': int(request.POST.get('max_volume', float('inf'))),
            
            # Fundamental data criteria
            'ranking_metric': request.POST.get('ranking_metric', 'eps'),  # EPS, PE, PB, ROE, etc.
            'income_statement_data': request.POST.getlist('income_statement_data'),
            'balance_sheet_data': request.POST.getlist('balance_sheet_data'),
            'cashflow_data': request.POST.getlist('cashflow_data'),
        }
        
        # Store configuration in session for processing
        request.session['backtest_config'] = backtest_data
        
        # Redirect to results page to run the backtest
        return redirect('strategies:equity_long_short_run_backtest')
    
    context = {
        'sectors': sectors_data,
    }
    
    return render(request, 'strategies/equity_long_short/backtest_config.html', context)


@login_required
def run_backtest(request):
    """
    Execute the backtest with configured parameters.
    """
    backtest_config = request.session.get('backtest_config')
    if not backtest_config:
        return redirect('strategies:equity_long_short_backtest_config')
    
    if request.method == 'POST':
        try:
            # Create portfolio
            portfolio = EquityLongShortPortfolio.objects.create(
                name=backtest_config['name'],
                user=request.user,
                strategy_type='equity_long_short',
                initial_capital=backtest_config['initial_capital'],
                start_date=backtest_config['start_date'],
                end_date=backtest_config['end_date'],
                universe_type='custom',
                long_target_weight=0.5,
                short_target_weight=0.5,
                rebalance_frequency='monthly'
            )
            
            # Run backtest with custom logic
            from strategies.strategies.equity_long_short import EquityLongShortStrategy
            strategy = EquityLongShortStrategy(portfolio)
            
            start_date = timezone.datetime.strptime(backtest_config['start_date'], '%Y-%m-%d').date()
            end_date = timezone.datetime.strptime(backtest_config['end_date'], '%Y-%m-%d').date()
            
            results = strategy.run_fundamental_backtest(
                start_date=start_date,
                end_date=end_date,
                total_stocks_holding=backtest_config['total_stocks_holding'],
                sectors=backtest_config['sectors'],
                min_market_cap=backtest_config['min_market_cap'],
                max_market_cap=backtest_config['max_market_cap'],
                min_stock_price=backtest_config['min_stock_price'],
                max_stock_price=backtest_config['max_stock_price'],
                min_volume=backtest_config['min_volume'],
                max_volume=backtest_config['max_volume'],
                ranking_metric=backtest_config['ranking_metric'],
                income_statement_data=backtest_config['income_statement_data'],
                balance_sheet_data=backtest_config['balance_sheet_data'],
                cashflow_data=backtest_config['cashflow_data']
            )
            
            # Save backtest results
            BacktestResult.objects.create(
                portfolio=portfolio,
                total_return=results['total_return'],
                annualized_return=results['annualized_return'],
                sharpe_ratio=results['sharpe_ratio'],
                max_drawdown=results['max_drawdown'],
                volatility=results['volatility'],
                total_trades=results.get('total_trades', 0),
                win_rate=results.get('win_rate', 0),
                avg_trade_return=results.get('avg_trade_return', 0),
            )
            
            # Store results in session for display
            request.session['backtest_results'] = results
            request.session['portfolio_id'] = portfolio.id
            
            return JsonResponse({
                'success': True,
                'portfolio_id': portfolio.id,
                'results': results
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    # GET request - show the backtest execution page
    context = {
        'config': backtest_config,
    }
    
    return render(request, 'strategies/equity_long_short/run_backtest.html', context)


@login_required
def backtest_results_display(request):
    """
    Display backtest results with performance comparison to S&P 500.
    """
    backtest_results = request.session.get('backtest_results')
    portfolio_id = request.session.get('portfolio_id')
    
    if not backtest_results or not portfolio_id:
        return redirect('strategies:equity_long_short_backtest_config')
    
    portfolio = EquityLongShortPortfolio.objects.get(id=portfolio_id, user=request.user)
    
    # Calculate percentage values for display
    results = backtest_results.copy()
    results['total_return_pct'] = results.get('total_return', 0) * 100
    results['annualized_return_pct'] = results.get('annualized_return', 0) * 100
    results['volatility_pct'] = results.get('volatility', 0) * 100
    results['max_drawdown_pct'] = results.get('max_drawdown', 0) * 100
    results['win_rate_pct'] = results.get('win_rate', 0) * 100
    results['avg_trade_return_pct'] = results.get('avg_trade_return', 0) * 100
    
    # Calculate portfolio values
    initial_capital = portfolio.initial_capital
    results['final_value'] = initial_capital * (1 + results.get('total_return', 0))
    results['sp500_final_value'] = initial_capital * 1.45  # 45% return for S&P 500
    
    # Calculate trade values
    trades = results.get('trades', [])
    for trade in trades:
        trade['total_value'] = trade.get('quantity', 0) * trade.get('price', 0)
    
    # Calculate additional metrics
    if results.get('volatility', 0) > 0:
        results['sortino_ratio'] = (results.get('total_return', 0) + 0.02) / results.get('volatility', 1)
        results['risk_adjusted_return'] = results.get('annualized_return', 0) / results.get('volatility', 1)
    else:
        results['sortino_ratio'] = 0
        results['risk_adjusted_return'] = 0
    
    context = {
        'portfolio': portfolio,
        'results': results,
        'performance_data': backtest_results.get('performance_data', []),
        'sp500_data': backtest_results.get('sp500_data', []),
    }
    
    return render(request, 'strategies/equity_long_short/backtest_results.html', context)


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
