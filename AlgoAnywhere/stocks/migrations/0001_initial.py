# Generated manually for Stock model

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Stock",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ticker", models.CharField(db_index=True, max_length=20, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("market_cap", models.BigIntegerField(blank=True, help_text="Market capitalization in USD", null=True)),
                ("sector", models.CharField(blank=True, max_length=100, null=True)),
            ],
            options={
                "verbose_name": "Stock",
                "verbose_name_plural": "Stocks",
                "ordering": ["ticker"],
            },
        ),
    ]
