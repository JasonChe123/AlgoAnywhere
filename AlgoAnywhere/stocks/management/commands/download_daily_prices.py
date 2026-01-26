from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from stocks.models import Stock, DailyPriceData
import yfinance as yf
import pandas as pd
import time
import re
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Optional
import warnings
from functools import wraps

# Suppress pandas/yfinance warnings
warnings.filterwarnings('ignore', category=FutureWarning, module='yfinance')
warnings.filterwarnings('ignore', category=pd.errors.PerformanceWarning)
warnings.filterwarnings('ignore', message='Timestamp.utcnow is deprecated')

# Set pandas to handle the deprecation warning
pd.set_option('future.no_silent_downcasting', True)

logger = logging.getLogger(__name__)

# Pattern to match invalid symbols (contains special characters other than letters and numbers)
INVALID_SYMBOL_PATTERN = re.compile(r'[^A-Za-z0-9\.]')


def _calculate_progress_metrics(items_processed, total_items, start_time):
    """
    Calculate progress bar and timing metrics.
    
    Args:
        items_processed (int): Number of items processed
        total_items (int): Total number of items to process
        start_time (float): Start time for elapsed calculation
        
    Returns:
        dict: Progress metrics including bar, percentage, timing info
    """
    percentage = min(100, (items_processed / total_items) * 100) if total_items > 0 else 0
    bar_length = 50
    filled_length = int(bar_length * percentage / 100)
    bar = "█" * filled_length + "░" * (bar_length - filled_length)
    
    elapsed = time.time() - start_time
    elapsed_min = int(elapsed // 60)
    elapsed_sec = int(elapsed % 60)
    
    if items_processed > 0:
        avg_time_per_item = elapsed / items_processed
        remaining_items = total_items - items_processed
        remaining_time = remaining_items * avg_time_per_item
        remaining_min = int(remaining_time // 60)
        remaining_sec = int(remaining_time % 60)
    else:
        remaining_min = 0
        remaining_sec = 0
    
    metrics = {
        'bar': bar,
        'percentage': percentage,
        'items_processed': items_processed,
        'total_items': total_items,
        'elapsed_min': elapsed_min,
        'elapsed_sec': elapsed_sec,
        'remaining_min': remaining_min,
        'remaining_sec': remaining_sec
    }
    
    return metrics


def _format_progress_line(metrics, complete=False):
    """
    Format progress line with bar and timing information.
    
    Args:
        metrics (dict): Progress metrics from _calculate_progress_metrics
        complete (bool): Whether processing is complete
        
    Returns:
        str: Formatted progress line
    """
    if metrics['items_processed'] > 0:
        if complete:
            return (f"\r📈  Progress: [{metrics['bar']}] {metrics['percentage']:.1f}% "
                   f"({metrics['items_processed']:,}/{metrics['total_items']:,}) | "
                   f"⏱️  {metrics['elapsed_min']:02d}:{metrics['elapsed_sec']:02d} elapsed | "
                   f"⏳ {metrics['remaining_min']:02d}:{metrics['remaining_sec']:02d} remaining | ✅ Complete!\r")
        else:
            return (f"\r  📈  Progress: [{metrics['bar']}] {metrics['percentage']:.1f}% "
                   f"({metrics['items_processed']:,}/{metrics['total_items']:,}) | "
                   f"⏱️  {metrics['elapsed_min']:02d}:{metrics['elapsed_sec']:02d} elapsed | "
                   f"⏳ {metrics['remaining_min']:02d}:{metrics['remaining_sec']:02d} remaining\r")
    else:
        return f"\r📈  Progress: [{metrics['bar']}] {metrics['percentage']:.1f}% ({metrics['items_processed']:,}/{metrics['total_items']:,})\r"


class Command(BaseCommand):
    help = "Download daily candlestick data for all stocks from Yahoo Finance with rate limiting"

    def add_arguments(self, parser):
        parser.add_argument(
            "--ticker",
            type=str,
            help="Download data for specific ticker only"
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="Number of stocks to process in each batch (default: 200)"
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.2,
            help="Delay between API calls in seconds (default: 0.2)"
        )
        parser.add_argument(
            "--start-date",
            type=str,
            help="Start date for historical data (YYYY-MM-DD format)"
        )
        parser.add_argument(
            "--end-date",
            type=str,
            help="End date for historical data (YYYY-MM-DD format)"
        )
        parser.add_argument(
            "--max-retries",
            type=int,
            default=3,
            help="Maximum number of retries for failed requests (default: 3)"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run without actually saving data to database"
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="Delete price data for stocks no longer in the database"
        )

    def handle(self, *args, **options):
        self.ticker = options.get("ticker")
        self.batch_size = options["batch_size"]
        self.delay = options["delay"]
        self.start_date = options.get("start_date")
        self.end_date = options.get("end_date")
        self.max_retries = options["max_retries"]
        self.dry_run = options["dry_run"]
        self.cleanup = options["cleanup"]
        
        # Set default date range to get maximum available data from yfinance
        if not self.end_date:
            self.end_date = timezone.now().date()
        else:
            self.end_date = datetime.strptime(self.end_date, "%Y-%m-%d").date()
            
        if not self.start_date:
            # Default to maximum available data (going back to 1970 when yfinance data typically starts)
            self.start_date = datetime(1970, 1, 1).date()
        else:
            self.start_date = datetime.strptime(self.start_date, "%Y-%m-%d").date()

        self.stdout.write(
            f"Downloading daily price data from {self.start_date} to {self.end_date}"
        )
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No data will be saved"))

        # Clean up orphaned price data if requested
        if self.cleanup:
            self._cleanup_orphaned_data()

        # Get stocks to process - defaults to ALL stocks if no ticker specified
        stocks = self._get_stocks()
        total_stocks = stocks.count()
        
        if total_stocks == 0:
            self.stdout.write(self.style.WARNING("No stocks found to process"))
            return

        self.stdout.write(f"Processing {total_stocks} stocks (downloading maximum available data)...")
        
        # Process in batches with optimized bulk downloading
        processed_count = 0
        failed_count = 0
        start_time = time.time()
        
        # Error tracking dictionary
        error_groups = {}
        
        for i in range(0, total_stocks, self.batch_size):
            batch = stocks[i:i + self.batch_size]
            batch_results = self._process_batch_optimized(batch)
            
            processed_count += batch_results['processed']
            failed_count += batch_results['failed']
            
            # Merge error groups
            if 'error_groups' in batch_results:
                for error_type, symbols in batch_results['error_groups'].items():
                    if error_type not in error_groups:
                        error_groups[error_type] = []
                    error_groups[error_type].extend(symbols)
            
            # Update progress bar
            current_progress = min(i + self.batch_size, total_stocks)
            metrics = _calculate_progress_metrics(current_progress, total_stocks, start_time)
            progress_line = _format_progress_line(metrics)
            self.stdout.write(progress_line, ending="\r")
            
            # Minimal delay between batches to avoid rate limiting
            if i + self.batch_size < total_stocks:
                time.sleep(self.delay)

        # Final progress update
        metrics = _calculate_progress_metrics(total_stocks, total_stocks, start_time)
        progress_line = _format_progress_line(metrics, complete=True)
        self.stdout.write(progress_line)
        self.stdout.write("")  # New line after progress bar

        # Display grouped errors
        if error_groups:
            self.stdout.write("\n" + "="*50)
            self.stdout.write("ERROR SUMMARY:")
            for error_type, symbols in error_groups.items():
                self.stdout.write(f"{error_type}: {', '.join(symbols[:10])}" + 
                                 (f" and {len(symbols)-10} more..." if len(symbols) > 10 else ""))

        # Summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write(f"SUMMARY:")
        self.stdout.write(f"Total stocks processed: {processed_count}")
        self.stdout.write(f"Failed downloads: {failed_count}")
        self.stdout.write(f"Success rate: {processed_count/(processed_count+failed_count)*100:.1f}%")
        
        if not self.dry_run:
            total_records = DailyPriceData.objects.filter(
                date__gte=self.start_date,
                date__lte=self.end_date
            ).count()
            self.stdout.write(f"Total price records in database: {total_records}")

    def _get_stocks(self):
        """Get stocks to process, filtering out symbols with special characters"""
        stocks = Stock.objects.all()
        
        # Filter out symbols with special characters (excluding dots which are valid in some symbols)
        valid_stocks = []
        invalid_symbols = []
        
        for stock in stocks:
            if INVALID_SYMBOL_PATTERN.search(stock.ticker):
                invalid_symbols.append(stock.ticker)
            else:
                valid_stocks.append(stock)
        
        if self.ticker:
            # Support multiple tickers separated by commas
            tickers = [t.strip().upper() for t in self.ticker.split(',')]
            # Filter valid tickers from the requested list
            valid_tickers = [t for t in tickers if not INVALID_SYMBOL_PATTERN.search(t)]
            invalid_requested = [t for t in tickers if INVALID_SYMBOL_PATTERN.search(t)]
            
            if invalid_requested:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping invalid symbols with special characters: {', '.join(invalid_requested)}"
                    )
                )
            
            stocks = stocks.filter(ticker__in=valid_tickers)
        else:
            stocks = Stock.objects.filter(id__in=[s.id for s in valid_stocks])
        
        # Report filtered symbols
        if invalid_symbols and not self.ticker:
            self.stdout.write(
                self.style.WARNING(
                    f"Filtered out {len(invalid_symbols)} symbols with special characters. "
                    f"Processing {len(valid_stocks)} valid symbols only."
                )
            )
        
        return stocks

    def _process_batch(self, stocks_batch):
        """Process a batch of stocks"""
        results = {'processed': 0, 'failed': 0}
        
        for stock in stocks_batch:
            try:
                success = self._download_stock_data(stock)
                if success:
                    results['processed'] += 1
                else:
                    results['failed'] += 1
                    
                # Delay between individual requests
                time.sleep(self.delay)
                
            except Exception as e:
                logger.error(f"Error processing {stock.ticker}: {e}")
                self.stdout.write(
                    self.style.ERROR(f"Error processing {stock.ticker}: {e}")
                )
                results['failed'] += 1
                
        return results

    def _process_batch_optimized(self, stocks_batch):
        """Process a batch of stocks using optimized bulk downloading"""
        results = {'processed': 0, 'failed': 0, 'error_groups': {}}
        
        try:
            # Get tickers for this batch
            tickers = [stock.ticker for stock in stocks_batch]
            ticker_str = ' '.join(tickers)
            
            # Download data for all tickers in this batch at once
            data = yf.download(
                ticker_str,
                start=self.start_date,
                end=self.end_date,
                interval="1d",
                group_by='ticker',
                progress=False  # Disable individual progress bars
            )
            
            if data.empty:
                self.stdout.write(f"No data available for batch")
                for stock in stocks_batch:
                    results['failed'] += 1
                    self._categorize_error(f"No data available", stock.ticker, results['error_groups'])
                return results
            
            # Process each ticker's data
            for stock in stocks_batch:
                try:
                    if stock.ticker in data.columns.get_level_values(0):
                        ticker_data = data[stock.ticker]
                        
                        # Skip if all NaN
                        if ticker_data.dropna(how='all').empty:
                            self.stdout.write(f"No valid data for {stock.ticker}")
                            results['failed'] += 1
                            self._categorize_error("No valid data", stock.ticker, results['error_groups'])
                            continue
                        
                        # Process and save data
                        success = self._process_historical_data_optimized(stock, ticker_data)
                        if success:
                            results['processed'] += 1
                        else:
                            results['failed'] += 1
                            self._categorize_error("Data processing failed", stock.ticker, results['error_groups'])
                    else:
                        self.stdout.write(f"No data column for {stock.ticker}")
                        results['failed'] += 1
                        self._categorize_error("No data column", stock.ticker, results['error_groups'])
                        
                except Exception as e:
                    error_msg = str(e)
                    self._categorize_error(error_msg, stock.ticker, results['error_groups'])
                    logger.error(f"Error processing {stock.ticker}: {e}")
                    results['failed'] += 1
                    
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error downloading batch data: {e}")
            self.stdout.write(f"Batch download failed: {e}")
            
            # Categorize batch error for all stocks in batch
            for stock in stocks_batch:
                self._categorize_error(error_msg, stock.ticker, results['error_groups'])
            
            # Fall back to individual downloads for this batch
            fallback_results = self._process_batch_fallback(stocks_batch)
            results['processed'] += fallback_results['processed']
            results['failed'] += fallback_results['failed']
            
            # Merge error groups from fallback
            if 'error_groups' in fallback_results:
                for error_type, symbols in fallback_results['error_groups'].items():
                    if error_type not in results['error_groups']:
                        results['error_groups'][error_type] = []
                    results['error_groups'][error_type].extend(symbols)
                
        return results

    def _process_batch_fallback(self, stocks_batch):
        """Fallback to individual downloads when batch download fails"""
        results = {'processed': 0, 'failed': 0, 'error_groups': {}}
        
        for stock in stocks_batch:
            try:
                success = self._download_stock_data(stock)
                if success:
                    results['processed'] += 1
                else:
                    results['failed'] += 1
                    self._categorize_error("Individual download failed", stock.ticker, results['error_groups'])
                    
                # Minimal delay between individual requests
                time.sleep(self.delay)
                
            except Exception as e:
                error_msg = str(e)
                self._categorize_error(error_msg, stock.ticker, results['error_groups'])
                logger.error(f"Error processing {stock.ticker}: {e}")
                results['failed'] += 1
                
        return results

    def _categorize_error(self, error_msg, ticker, error_groups):
        """Categorize errors by type for better reporting"""
        error_msg_lower = error_msg.lower()
        
        # Common error patterns
        if "possibly delisted" in error_msg_lower or "no timezone found" in error_msg_lower:
            error_type = "possibly delisted; no timezone found"
        elif "not found" in error_msg_lower or "404" in error_msg_lower:
            error_type = "HTTP Error 404: Quote not found"
        elif "too many requests" in error_msg_lower or "rate limit" in error_msg_lower:
            error_type = "Rate limit exceeded"
        elif "no data" in error_msg_lower:
            error_type = "No data available"
        elif "timeout" in error_msg_lower:
            error_type = "Request timeout"
        else:
            # Extract first 50 chars of error message for unknown errors
            error_type = error_msg[:50] + "..." if len(error_msg) > 50 else error_msg
        
        if error_type not in error_groups:
            error_groups[error_type] = []
        error_groups[error_type].append(ticker)

    def _download_stock_data(self, stock):
        """Download data for a single stock with retry logic"""
        for attempt in range(self.max_retries):
            try:
                # Download data using yfinance
                ticker_obj = yf.Ticker(stock.ticker)
                
                # Get historical data
                hist_data = ticker_obj.history(
                    start=self.start_date,
                    end=self.end_date,
                    interval="1d"
                )
                
                if hist_data.empty:
                    self.stdout.write(
                        self.style.WARNING(f"No data available for {stock.ticker}")
                    )
                    return False
                
                # Process and save data
                return self._process_historical_data(stock, hist_data)
                
            except Exception as e:
                if attempt == self.max_retries - 1:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to download {stock.ticker} after {self.max_retries} attempts: {e}"
                        )
                    )
                    return False
                    
                # Exponential backoff
                wait_time = (2 ** attempt) * self.delay
                self.stdout.write(
                    f"Retry {attempt + 1}/{self.max_retries} for {stock.ticker} after {wait_time}s..."
                )
                time.sleep(wait_time)
        
        return False

    def _process_historical_data_optimized(self, stock, ticker_data):
        """Process historical data efficiently for bulk operations"""
        try:
            # Prepare data for bulk creation
            price_records = []
            
            # Get existing dates for this stock to avoid duplicates
            if not self.dry_run:
                existing_dates = set(
                    DailyPriceData.objects.filter(stock=stock).values_list('date', flat=True)
                )
            else:
                existing_dates = set()
            
            for date, row in ticker_data.iterrows():
                # Convert to date object (remove time component)
                trade_date = date.date()
                
                # Skip if we already have this data
                if trade_date in existing_dates:
                    continue
                
                # Skip if all values are NaN
                if pd.isna(row['Open']) and pd.isna(row['Close']):
                    continue
                
                # Create record
                price_records.append(DailyPriceData(
                    stock=stock,
                    date=trade_date,
                    open_price=round(float(row['Open']), 4) if pd.notna(row['Open']) else None,
                    high_price=round(float(row['High']), 4) if pd.notna(row['High']) else None,
                    low_price=round(float(row['Low']), 4) if pd.notna(row['Low']) else None,
                    close_price=round(float(row['Close']), 4) if pd.notna(row['Close']) else None,
                    adjusted_close=round(float(row['Close']), 4) if pd.notna(row['Close']) else None,
                    volume=int(row['Volume']) if pd.notna(row['Volume']) and row['Volume'] > 0 else None,
                ))
            
            if not price_records:
                return True
            
            if self.dry_run:
                return True
            
            # Bulk create records with larger batch size
            with transaction.atomic():
                DailyPriceData.objects.bulk_create(
                    price_records,
                    batch_size=1000,  # Increased batch size
                    ignore_conflicts=True
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing data for {stock.ticker}: {e}")
            return False

    def _process_historical_data(self, stock, hist_data):
        """Process historical data and save to database"""
        try:
            # Prepare data for bulk creation
            price_records = []
            
            # Get existing dates for this stock to avoid duplicates (more efficient)
            if not self.dry_run:
                existing_dates = set(
                    DailyPriceData.objects.filter(stock=stock).values_list('date', flat=True)
                )
            else:
                existing_dates = set()
            
            for date, row in hist_data.iterrows():
                # Convert to date object (remove time component)
                trade_date = date.date()
                
                # Skip if we already have this data
                if trade_date in existing_dates:
                    continue
                
                # Create record
                price_records.append(DailyPriceData(
                    stock=stock,
                    date=trade_date,
                    open_price=round(float(row['Open']), 4) if pd.notna(row['Open']) else None,
                    high_price=round(float(row['High']), 4) if pd.notna(row['High']) else None,
                    low_price=round(float(row['Low']), 4) if pd.notna(row['Low']) else None,
                    close_price=round(float(row['Close']), 4) if pd.notna(row['Close']) else None,
                    adjusted_close=round(float(row['Close']), 4) if pd.notna(row['Close']) else None,  # yfinance uses Close as Adj Close
                    volume=int(row['Volume']) if pd.notna(row['Volume']) else None,
                ))
            
            if not price_records:
                self.stdout.write(f"No new data for {stock.ticker}")
                return True
            
            if self.dry_run:
                self.stdout.write(
                    f"DRY RUN: Would save {len(price_records)} records for {stock.ticker}"
                )
                return True
            
            # Bulk create records with larger batch size
            with transaction.atomic():
                DailyPriceData.objects.bulk_create(
                    price_records,
                    batch_size=1000,  # Increased from 500
                    ignore_conflicts=True  # Skip duplicates
                )
            
            self.stdout.write(
                f"Saved {len(price_records)} records for {stock.ticker}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Error processing data for {stock.ticker}: {e}")
            self.stdout.write(
                self.style.ERROR(f"Error processing data for {stock.ticker}: {e}")
            )
            return False

    def _cleanup_orphaned_data(self):
        """Delete price data for stocks no longer in the database"""
        self.stdout.write("Cleaning up orphaned price data...")
        
        if self.dry_run:
            # Just show what would be deleted
            orphaned_count = DailyPriceData.objects.exclude(
                stock_id__in=Stock.objects.values_list('id', flat=True)
            ).count()
            self.stdout.write(
                f"DRY RUN: Would delete {orphaned_count} orphaned price records"
            )
            return
        
        # Actually delete orphaned data
        deleted_count, _ = DailyPriceData.objects.exclude(
            stock_id__in=Stock.objects.values_list('id', flat=True)
        ).delete()
        
        if deleted_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f"Deleted {deleted_count} orphaned price records")
            )
        else:
            self.stdout.write("No orphaned price data found")
