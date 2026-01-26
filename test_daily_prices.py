#!/usr/bin/env python3
"""
Test script for the daily price download functionality.
This script demonstrates how to use the download_daily_prices management command.
"""

import os
import sys
import django
from django.core.management import call_command

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AlgoAnywhere.settings')
sys.path.append('/home/jasonche/Documents/Git-Repository/AlgoAnywhere/AlgoAnywhere')

# Activate virtual environment
os.system('source /home/jasonche/Documents/Git-Repository/AlgoAnywhere/venv/bin/activate')

django.setup()

def test_download_command():
    """Test the download_daily_prices command with various options"""
    
    print("Testing Daily Price Download Command")
    print("=" * 50)
    
    # Test 1: Dry run with a specific ticker
    print("\n1. Testing dry run with AAPL...")
    try:
        call_command('download_daily_prices', 
                    ticker='AAPL',
                    dry_run=True,
                    delay=0.1,
                    start_date='2024-01-01',
                    end_date='2024-01-31')
        print("✓ Dry run completed successfully")
    except Exception as e:
        print(f"✗ Dry run failed: {e}")
    
    # Test 2: Cleanup functionality test
    print("\n2. Testing cleanup functionality...")
    try:
        call_command('download_daily_prices',
                    cleanup=True,
                    dry_run=True,
                    delay=0.1)
        print("✓ Cleanup test completed successfully")
    except Exception as e:
        print(f"✗ Cleanup test failed: {e}")
    
    # Test 3: Small batch download with maximum data
    print("\n3. Testing small batch download...")
    try:
        call_command('download_daily_prices',
                    ticker='MSFT',
                    delay=0.2,
                    batch_size=1,
                    start_date='2024-01-01',
                    end_date='2024-01-10')
        print("✓ Small batch download completed successfully")
    except Exception as e:
        print(f"✗ Small batch download failed: {e}")
    
    # Test 4: Check if data was saved
    print("\n4. Verifying saved data...")
    try:
        from stocks.models import DailyPriceData, Stock
        
        # Check if we have any price data
        price_count = DailyPriceData.objects.count()
        print(f"Total price records in database: {price_count}")
        
        if price_count > 0:
            # Show some sample data
            latest_prices = DailyPriceData.objects.select_related('stock').order_by('-date')[:5]
            print("\nLatest price records:")
            for price in latest_prices:
                print(f"  {price.stock.ticker} - {price.date}: ${price.close_price} (Vol: {price.volume})")
        
        print("✓ Data verification completed")
    except Exception as e:
        print(f"✗ Data verification failed: {e}")
    
    # Test 5: Test default behavior (all stocks, max data)
    print("\n5. Testing default behavior (dry run)...")
    try:
        call_command('download_daily_prices',
                    dry_run=True,
                    delay=0.1,
                    batch_size=5)
        print("✓ Default behavior test completed successfully")
    except Exception as e:
        print(f"✗ Default behavior test failed: {e}")

if __name__ == '__main__':
    test_download_command()
