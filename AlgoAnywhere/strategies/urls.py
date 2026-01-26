"""
URL configuration for strategies app.
"""

from django.urls import path
from .views import equity_long_short

app_name = 'strategies'

urlpatterns = [
    # Equity Long-Short Strategy URLs
    path('equity-long-short/', equity_long_short.equity_long_short_home, name='equity_long_short_home'),
    path('equity-long-short/create/', equity_long_short.create_portfolio, name='equity_long_short_create'),
    path('equity-long-short/backtest/<int:portfolio_id>/', equity_long_short.backtest_strategy, name='equity_long_short_backtest'),
    path('equity-long-short/results/<int:portfolio_id>/', equity_long_short.portfolio_results, name='equity_long_short_results'),
    path('equity-long-short/basket/', equity_long_short.generate_basket_order, name='equity_long_short_generate_basket'),
    path('equity-long-short/basket/<int:basket_order_id>/', equity_long_short.basket_order_detail, name='basket_order_detail'),
    path('equity-long-short/basket/<int:basket_order_id>/download/<str:format_type>/', 
         equity_long_short.download_basket_order, name='download_basket_order'),
    path('equity-long-short/universes/', equity_long_short.manage_universes, name='manage_universes'),
    
    # API endpoints
    path('api/equity-long-short/performance/<int:portfolio_id>/', 
         equity_long_short.api_portfolio_performance, name='api_portfolio_performance'),
    path('api/equity-long-short/signals/<int:portfolio_id>/', 
         equity_long_short.api_current_signals, name='api_current_signals'),
]
