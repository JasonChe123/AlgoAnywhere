# Generated migration to add unique constraint on fiscal period

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stocks', '0003_rename_stocks_inco_stock_i_abc123_idx_stocks_inco_stock_i_078442_idx_and_more'),
    ]

    operations = [
        # First, remove existing unique constraint that includes period_end_date
        migrations.RunSQL(
            "ALTER TABLE stocks_incomestatement DROP CONSTRAINT IF EXISTS stocks_incomestatement_stock_id_period_end_date_22c9bd4a_uniq;",
            reverse_sql="SELECT 1;"  # No-op for reverse
        ),
        
        # Add new unique constraint on just fiscal period
        migrations.AddConstraint(
            model_name='incomestatement',
            constraint=models.UniqueConstraint(
                fields=['stock', 'fiscal_year', 'fiscal_quarter'],
                name='unique_fiscal_period'
            ),
        ),
    ]
