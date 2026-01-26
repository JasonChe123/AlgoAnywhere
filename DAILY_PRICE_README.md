# Daily Price Data Download

This document describes the functionality for downloading daily candlestick data from Yahoo Finance for all stocks in the database.

## Features

- **Bulk Download**: Efficiently downloads data for multiple stocks in batches
- **Live Progress Bar**: Real-time progress tracking with time estimates and completion percentage
- **Rate Limiting**: Built-in delays to avoid being banned by Yahoo Finance
- **Error Handling**: Retry logic with exponential backoff for failed requests
- **Flexible Date Range**: Download data for any specified period
- **Dry Run Mode**: Test the download without saving to database
- **Duplicate Prevention**: Automatically skips existing data
- **Orphaned Data Cleanup**: Remove price data for stocks no longer in database

## Data Model

The `DailyPriceData` model stores the following fields:
- `stock`: Foreign key to Stock model
- `date`: Trading date
- `open_price`: Opening price
- `high_price`: Highest price of the day
- `low_price`: Lowest price of the day
- `close_price`: Closing price
- `adjusted_close`: Adjusted closing price (dividends/splits)
- `volume`: Trading volume
- `created_at`: Record creation timestamp
- `updated_at`: Record update timestamp

## Usage

### Management Command

Use the `download_daily_prices` management command:

```bash
# Download maximum available data for ALL stocks (default behavior)
python manage.py download_daily_prices

# Download for specific ticker (supports multiple tickers with commas)
python manage.py download_daily_prices --ticker AAPL
python manage.py download_daily_prices --ticker AAPL,MSFT,GOOGL

# Custom date range
python manage.py download_daily_prices --start-date 2023-01-01 --end-date 2023-12-31

# Clean up orphaned data (stocks no longer in database)
python manage.py download_daily_prices --cleanup

# Adjust batch size and delay for rate limiting
python manage.py download_daily_prices --batch-size 50 --delay 1.0

# Dry run (test without saving)
python manage.py download_daily_prices --dry-run

# Increase retry attempts for unreliable connections
python manage.py download_daily_prices --max-retries 5

# Combined cleanup and download
python manage.py download_daily_prices --cleanup --batch-size 100
```

### Command Options

- `--ticker`: Download data for specific ticker only
- `--batch-size`: Number of stocks to process in each batch (default: 100)
- `--delay`: Delay between API calls in seconds (default: 0.5)
- `--start-date`: Start date for historical data (YYYY-MM-DD format)
- `--end-date`: End date for historical data (YYYY-MM-DD format)
- `--max-retries`: Maximum number of retries for failed requests (default: 3)
- `--dry-run`: Run without actually saving data to database
- `--cleanup`: Delete price data for stocks no longer in the database

## Default Behavior

- **Date Range**: Downloads maximum available data from 1970-01-01 to today
- **Stocks**: Processes ALL stocks in the database by default
- **Cleanup**: Only runs when explicitly requested with `--cleanup` flag

## Rate Limiting Strategy

To avoid being banned by Yahoo Finance:

1. **Individual Request Delays**: 0.5 second delay between each stock request
2. **Batch Delays**: 1 second delay between batches
3. **Exponential Backoff**: Retry failed requests with increasing delays
4. **Bulk Operations**: Use database bulk_create for efficient storage

## Error Handling

- **Network Errors**: Automatic retry with exponential backoff
- **Missing Data**: Graceful handling when no data is available
- **Invalid Tickers**: Skip and continue with other stocks
- **Database Errors**: Transaction rollback on batch failures

## Performance Considerations

- **Batch Processing**: Processes stocks in configurable batch sizes
- **Bulk Database Operations**: Uses Django's bulk_create for efficient inserts
- **Memory Efficient**: Processes data in chunks to avoid memory issues
- **Duplicate Prevention**: Uses `ignore_conflicts=True` to skip duplicates

## Example Output

```
Downloading daily price data from 1970-01-01 to 2024-01-24
DRY RUN MODE - No data will be saved
Processing 5000 stocks (downloading maximum available data)...
DRY RUN: Would save 252 records for AAPL
  📈  Progress: [████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 33.3% (1667/5000) | ⏱️  05:23 elapsed | ⏳  10:47 remaining
DRY RUN: Would save 248 records for MSFT
  📈  Progress: [█████████████████████████████████░░░░░░░░░░░░░░░░░] 66.7% (3333/5000) | ⏱️  10:46 elapsed | ⏳  05:23 remaining
DRY RUN: Would save 248 records for GOOGL
📈  Progress: [██████████████████████████████████████████████████] 100.0% (5000/5000) | ⏱️  16:09 elapsed | ⏳  00:00 remaining | ✅ Complete!

==================================================
SUMMARY:
Total stocks processed: 4950
Failed downloads: 50
Success rate: 99.0%
Total price records in database: 1,247,500
```

## Testing

Run the test script to verify functionality:

```bash
python test_daily_prices.py
```

## Monitoring

Monitor the download progress and success rate through the command output. Check the database for:

```sql
-- Count total records
SELECT COUNT(*) FROM stocks_dailypricedata;

-- Check latest data
SELECT stock_id, date, close_price, volume 
FROM stocks_dailypricedata 
ORDER BY date DESC 
LIMIT 10;

-- Check data coverage per stock
SELECT stock_id, COUNT(*) as days_count,
       MIN(date) as start_date,
       MAX(date) as end_date
FROM stocks_dailypricedata 
GROUP BY stock_id;
```
