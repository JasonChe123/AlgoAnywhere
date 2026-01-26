from django.core.management.base import BaseCommand
from stocks.models import IncomeStatement


class Command(BaseCommand):
    help = "Reset all income statement data"

    def handle(self, *args, **options):
        count = IncomeStatement.objects.count()
        self.stdout.write(f"Deleting {count} income statement records...")
        IncomeStatement.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("All income statement data deleted."))
