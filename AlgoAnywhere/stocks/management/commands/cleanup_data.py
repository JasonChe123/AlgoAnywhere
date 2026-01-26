from django.core.management.base import BaseCommand
from django.db.models import Count
from stocks.models import IncomeStatement, Stock
from collections import defaultdict
import yfinance as yf


class Command(BaseCommand):
    help = "Analyze and clean up duplicate/inconsistent income statement data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--analyze",
            action="store_true",
            help="Analyze current data for duplicates and inconsistencies"
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="Clean up duplicate records"
        )
        parser.add_argument(
            "--verify",
            action="store_true",
            help="Verify data against Yahoo Finance"
        )
        parser.add_argument(
            "--ticker",
            type=str,
            help="Process specific ticker only"
        )

    def handle(self, *args, **options):
        if options["analyze"]:
            self.analyze_data(options.get("ticker"))
        elif options["cleanup"]:
            self.cleanup_data(options.get("ticker"))
        elif options["verify"]:
            self.verify_data(options.get("ticker"))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Specify --analyze, --cleanup, or --verify"
                )
            )

    def analyze_data(self, ticker=None):
        """Analyze current data for duplicates and inconsistencies"""
        self.stdout.write("Analyzing income statement data...")
        
        # Get all stocks or specific ticker
        stocks = Stock.objects.all()
        if ticker:
            stocks = stocks.filter(ticker=ticker.upper())
        
        total_issues = 0
        
        for stock in stocks:
            # Group by fiscal year, quarter, and form type
            duplicates = IncomeStatement.objects.filter(stock=stock).values(
                'fiscal_year', 'fiscal_quarter', 'form_type'
            ).annotate(
                count=Count('id'),
                unique_dates=Count('period_end_date', distinct=True)
            ).filter(
                count__gt=1
            )
            
            if duplicates.exists():
                self.stdout.write(f"\n{stock.ticker} - Found duplicates:")
                for dup in duplicates:
                    self.stdout.write(
                        f"  FY{dup['fiscal_year']} Q{dup['fiscal_quarter']} "
                        f"{dup['form_type']}: {dup['count']} records, "
                        f"{dup['unique_dates']} unique dates"
                    )
                    
                    # Show the actual records
                    records = IncomeStatement.objects.filter(
                        stock=stock,
                        fiscal_year=dup['fiscal_year'],
                        fiscal_quarter=dup['fiscal_quarter'],
                        form_type=dup['form_type']
                    ).order_by('period_end_date')
                    
                    for record in records:
                        revenue_str = f"{record.revenue:,}" if record.revenue else "None"
                        net_income_str = f"{record.net_income:,}" if record.net_income else "None"
                        self.stdout.write(
                            f"    {record.period_end_date}: "
                            f"Revenue={revenue_str}, "
                            f"Net Income={net_income_str}"
                        )
                
                total_issues += duplicates.count()
        
        if total_issues == 0:
            self.stdout.write(self.style.SUCCESS("No duplicate records found!"))
        else:
            self.stdout.write(
                self.style.WARNING(f"Found {total_issues} duplicate groups")
            )

    def cleanup_data(self, ticker=None):
        """Clean up duplicate records"""
        self.stdout.write("Cleaning up duplicate records...")
        
        stocks = Stock.objects.all()
        if ticker:
            stocks = stocks.filter(ticker=ticker.upper())
        
        total_deleted = 0
        
        for stock in stocks:
            # Find duplicates
            duplicates = IncomeStatement.objects.filter(stock=stock).values(
                'fiscal_year', 'fiscal_quarter', 'form_type'
            ).annotate(
                count=Count('id')
            ).filter(
                count__gt=1
            )
            
            for dup in duplicates:
                # Get all records for this duplicate group
                records = IncomeStatement.objects.filter(
                    stock=stock,
                    fiscal_year=dup['fiscal_year'],
                    fiscal_quarter=dup['fiscal_quarter'],
                    form_type=dup['form_type']
                ).order_by('-filing_date', '-period_end_date')
                
                if records.count() > 1:
                    # Keep the most recent filing, delete the rest
                    to_keep = records.first()
                    to_delete = records[1:]
                    
                    self.stdout.write(
                        f"{stock.ticker} FY{dup['fiscal_year']} "
                        f"Q{dup['fiscal_quarter']} {dup['form_type']}: "
                        f"keeping {to_keep.period_end_date}, "
                        f"deleting {to_delete.count()} records"
                    )
                    
                    # Get IDs to delete and delete them in a separate query
                    delete_ids = list(to_delete.values_list('id', flat=True))
                    deleted_count = len(delete_ids)
                    IncomeStatement.objects.filter(id__in=delete_ids).delete()
                    total_deleted += deleted_count
        
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {total_deleted} duplicate records")
        )

    def verify_data(self, ticker=None):
        """Verify data against Yahoo Finance"""
        self.stdout.write("Verifying data against Yahoo Finance...")
        
        stocks = Stock.objects.all()
        if ticker:
            stocks = stocks.filter(ticker=ticker.upper())
        
        # Limit to first few stocks for testing
        stocks = stocks[:5]
        
        for stock in stocks:
            try:
                self.stdout.write(f"\nChecking {stock.ticker}...")
                
                # Get latest quarterly data from database
                latest_db = IncomeStatement.objects.filter(
                    stock=stock,
                    fiscal_quarter__isnull=False
                ).order_by('-fiscal_year', '-fiscal_quarter').first()
                
                if not latest_db:
                    self.stdout.write(f"  No quarterly data found for {stock.ticker}")
                    continue
                
                # Get data from Yahoo Finance
                ticker_obj = yf.Ticker(stock.ticker)
                
                # Try to get financial data
                financials = ticker_obj.financials
                quarterly_financials = ticker_obj.quarterly_financials
                
                if financials is not None and not financials.empty:
                    latest_yahoo_revenue = financials.loc['Total Revenue'].iloc[0]
                    latest_yahoo_net_income = financials.loc['Net Income'].iloc[0]
                    
                    self.stdout.write(
                        f"  Latest DB Data (FY{latest_db.fiscal_year} Q{latest_db.fiscal_quarter}):"
                    )
                    self.stdout.write(f"    Revenue: ${latest_db.revenue:,}")
                    self.stdout.write(f"    Net Income: ${latest_db.net_income:,}")
                    
                    self.stdout.write(f"  Yahoo Finance Data:")
                    self.stdout.write(f"    Revenue: ${latest_yahoo_revenue:,.0f}")
                    self.stdout.write(f"    Net Income: ${latest_yahoo_net_income:,.0f}")
                    
                    # Check for significant differences
                    if latest_db.revenue and latest_yahoo_revenue:
                        rev_diff = abs(latest_db.revenue - latest_yahoo_revenue) / latest_yahoo_revenue
                        if rev_diff > 0.1:  # 10% difference threshold
                            self.stdout.write(
                                self.style.WARNING(
                                    f"    Revenue difference: {rev_diff:.1%}"
                                )
                            )
                    
                    if latest_db.net_income and latest_yahoo_net_income:
                        inc_diff = abs(latest_db.net_income - latest_yahoo_net_income) / abs(latest_yahoo_net_income)
                        if inc_diff > 0.1:  # 10% difference threshold
                            self.stdout.write(
                                self.style.WARNING(
                                    f"    Net Income difference: {inc_diff:.1%}"
                                )
                            )
                else:
                    self.stdout.write(f"  No Yahoo Finance data available for {stock.ticker}")
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  Error verifying {stock.ticker}: {e}")
                )
