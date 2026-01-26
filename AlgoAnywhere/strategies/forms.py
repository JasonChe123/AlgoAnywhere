"""
Forms for strategies app.

This module provides Django forms for user input in strategy creation,
parameter configuration, and universe management.
"""

from django import forms
from django.core.validators import MinValueValidator, MaxValueValidator
from stocks.models import Stock


class EquityLongShortPortfolioForm(forms.Form):
    """
    Form for creating equity long-short portfolios.
    """
    name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Portfolio Name'})
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Portfolio Description'})
    )
    initial_capital = forms.DecimalField(
        initial=1000000,
        min_value=10000,
        max_value=100000000,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '10000'})
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    
    # Universe selection
    UNIVERSE_CHOICES = [
        ('sp500', 'S&P 500'),
        ('russell1000', 'Russell 1000'),
        ('russell2000', 'Russell 2000'),
        ('custom', 'Custom Universe'),
    ]
    universe_type = forms.ChoiceField(
        choices=UNIVERSE_CHOICES,
        initial='sp500',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    # Position sizing
    long_target_weight = forms.DecimalField(
        initial=0.50,
        min_value=0.1,
        max_value=1.0,
        validators=[MinValueValidator(0.1), MaxValueValidator(1.0)],
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    short_target_weight = forms.DecimalField(
        initial=0.50,
        min_value=0.1,
        max_value=1.0,
        validators=[MinValueValidator(0.1), MaxValueValidator(1.0)],
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    max_position_weight = forms.DecimalField(
        initial=0.05,
        min_value=0.01,
        max_value=0.20,
        validators=[MinValueValidator(0.01), MaxValueValidator(0.20)],
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    # Rebalancing
    REBALANCE_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ]
    rebalance_frequency = forms.ChoiceField(
        choices=REBALANCE_CHOICES,
        initial='monthly',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    # Risk management
    beta_neutral = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    sector_neutral = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    max_leverage = forms.DecimalField(
        initial=2.0,
        min_value=1.0,
        max_value=5.0,
        validators=[MinValueValidator(1.0), MaxValueValidator(5.0)],
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        long_weight = cleaned_data.get('long_target_weight')
        short_weight = cleaned_data.get('short_target_weight')
        
        if long_weight and short_weight:
            total_weight = long_weight + short_weight
            if abs(total_weight - 1.0) > 0.01:  # Allow small rounding error
                raise forms.ValidationError(
                    f'Long and short weights must sum to 1.0 (currently {total_weight:.2f})'
                )
        
        return cleaned_data


class BacktestForm(forms.Form):
    """
    Form for running backtests.
    """
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if start_date >= end_date:
                raise forms.ValidationError('End date must be after start date')
            
            if (end_date - start_date).days < 30:
                raise forms.ValidationError('Backtest period must be at least 30 days')
        
        return cleaned_data


class BasketOrderForm(forms.Form):
    """
    Form for generating basket orders.
    """
    order_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )


class EquityUniverseForm(forms.Form):
    """
    Form for creating custom stock universes.
    """
    name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Universe Name'})
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Universe Description'})
    )
    stock_tickers = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control', 
            'rows': 10,
            'placeholder': 'Enter stock tickers, one per line:\nAAPL\nMSFT\nGOOGL\n...'
        })
    )
    
    # Universe criteria
    min_market_cap = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '1000000'})
    )
    max_market_cap = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '1000000'})
    )
    min_price = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    exclude_etfs = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    exclude_adrs = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def clean_stock_tickers(self):
        """
        Validate and clean stock tickers.
        """
        tickers = self.cleaned_data['stock_tickers']
        ticker_list = [ticker.strip() for ticker in tickers.split('\n') if ticker.strip()]
        
        # Validate tickers exist in database
        valid_tickers = []
        invalid_tickers = []
        
        for ticker in ticker_list:
            if Stock.objects.filter(ticker=ticker).exists():
                valid_tickers.append(ticker)
            else:
                invalid_tickers.append(ticker)
        
        if invalid_tickers:
            raise forms.ValidationError(
                f'The following tickers were not found: {", ".join(invalid_tickers)}'
            )
        
        return '\n'.join(valid_tickers)
    
    def clean(self):
        cleaned_data = super().clean()
        min_cap = cleaned_data.get('min_market_cap')
        max_cap = cleaned_data.get('max_market_cap')
        
        if min_cap and max_cap and min_cap >= max_cap:
            raise forms.ValidationError('Minimum market cap must be less than maximum market cap')
        
        return cleaned_data


class StrategyParameterForm(forms.Form):
    """
    Form for strategy parameter optimization.
    """
    # Factor weights
    value_weight = forms.DecimalField(
        initial=0.25,
        min_value=0,
        max_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    momentum_weight = forms.DecimalField(
        initial=0.25,
        min_value=0,
        max_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    quality_weight = forms.DecimalField(
        initial=0.25,
        min_value=0,
        max_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    growth_weight = forms.DecimalField(
        initial=0.25,
        min_value=0,
        max_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    # Universe parameters
    universe_percentile = forms.IntegerField(
        initial=10,
        min_value=5,
        max_value=25,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    # Risk parameters
    max_leverage = forms.DecimalField(
        initial=2.0,
        min_value=1.0,
        max_value=5.0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        weights = [
            cleaned_data.get('value_weight', 0),
            cleaned_data.get('momentum_weight', 0),
            cleaned_data.get('quality_weight', 0),
            cleaned_data.get('growth_weight', 0),
        ]
        
        total_weight = sum(weights)
        if abs(total_weight - 1.0) > 0.01:
            raise forms.ValidationError(
                f'Factor weights must sum to 1.0 (currently {total_weight:.2f})'
            )
        
        return cleaned_data
