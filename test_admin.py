#!/usr/bin/env python3
"""
Test script to verify DailyPriceData is accessible in Django admin
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AlgoAnywhere.settings')
sys.path.append('/home/jasonche/Documents/Git-Repository/AlgoAnywhere/AlgoAnywhere')

django.setup()

def test_admin():
    """Test that DailyPriceData is properly registered in admin"""
    try:
        from django.contrib import admin
        from stocks.models import DailyPriceData
        
        # Check if model is registered
        print("🔍 Checking Django Admin Registration")
        print("=" * 50)
        
        # Check if model is registered in admin
        is_registered = admin.site.is_registered(DailyPriceData)
        print(f"📋 DailyPriceData registered in admin: {is_registered}")
        
        if is_registered:
            admin_class = admin.site._registry[DailyPriceData]
            print(f"🎛️  Admin class: {admin_class.__class__.__name__}")
            print(f"📊 List display fields: {admin_class.list_display}")
            print(f"🔍 Search fields: {admin_class.search_fields}")
            print(f"📅 Date hierarchy: {admin_class.date_hierarchy}")
            print(f"🔧 Raw ID fields: {admin_class.raw_id_fields}")
        
        # Test model access
        print(f"\n📈 Testing model access...")
        count = DailyPriceData.objects.count()
        print(f"📊 Total DailyPriceData records: {count:,}")
        
        # Test recent data
        recent = DailyPriceData.objects.select_related('stock').order_by('-date')[:3]
        print(f"📅 Recent records:")
        for dp in recent:
            print(f"  {dp.stock.ticker}: {dp.date} @ ${dp.close_price}")
        
        print(f"\n✅ Admin registration test complete!")
        print(f"🌐 You should now see 'Daily Price Data' in your Django admin at /admin/")
        
    except Exception as e:
        print(f"❌ Error testing admin: {e}")

if __name__ == '__main__':
    test_admin()
