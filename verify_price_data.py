#!/usr/bin/env python3
"""
Quick script to verify daily price data exists in database
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AlgoAnywhere.settings')
sys.path.append('/home/jasonche/Documents/Git-Repository/AlgoAnywhere/AlgoAnywhere')

# Activate virtual environment
os.system('source /home/jasonche/Documents/Git-Repository/AlgoAnywhere/venv/bin/activate')

django.setup()

def verify_data():
    """Verify daily price data exists"""
    try:
        from stocks.models import DailyPriceData, Stock
        from django.db.models import Min, Max, Count
        
        print("🔍 Verifying Daily Price Data")
        print("=" * 50)
        
        # Check table exists
        total_records = DailyPriceData.objects.count()
        print(f"📊 Total price records: {total_records:,}")
        
        # Check stocks with data
        stocks_with_data = DailyPriceData.objects.values('stock_id').distinct().count()
        total_stocks = Stock.objects.count()
        print(f"🏢 Stocks with price data: {stocks_with_data:,}/{total_stocks:,}")
        
        # Date range
        date_range = DailyPriceData.objects.aggregate(
            min_date=Min('date'),
            max_date=Max('date')
        )
        print(f"📅 Date range: {date_range['min_date']} to {date_range['max_date']}")
        
        # Sample recent data
        recent_data = DailyPriceData.objects.select_related('stock').order_by('-date')[:10]
        print(f"\n📈 Recent price data:")
        for dp in recent_data:
            print(f"  {dp.stock.ticker}: {dp.date} - ${dp.close_price} (Vol: {dp.volume:,})")
        
        # Check specific popular stocks
        popular_tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
        print(f"\n🔥 Popular stocks data:")
        for ticker in popular_tickers:
            count = DailyPriceData.objects.filter(stock__ticker=ticker).count()
            if count > 0:
                latest = DailyPriceData.objects.filter(stock__ticker=ticker).order_by('-date').first()
                print(f"  {ticker}: {count:,} records, latest: {latest.date} @ ${latest.close_price}")
            else:
                print(f"  {ticker}: No data")
        
        print(f"\n✅ Data verification complete!")
        
    except Exception as e:
        print(f"❌ Error verifying data: {e}")

if __name__ == '__main__':
    verify_data()
