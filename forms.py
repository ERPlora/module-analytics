from django import forms
from django.utils.translation import gettext_lazy as _

from .models import AnalyticsSettings, SavedReport


class AnalyticsSettingsForm(forms.ModelForm):
    """Form for analytics module settings."""

    class Meta:
        model = AnalyticsSettings
        fields = [
            'default_period',
            'default_currency',
            'show_profit',
            'show_tax_breakdown',
            'compare_previous_period',
            'fiscal_year_start_month',
        ]
        widgets = {
            'default_period': forms.Select(attrs={
                'class': 'select',
            }),
            'default_currency': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': _('EUR'),
                'maxlength': '3',
            }),
            'show_profit': forms.CheckboxInput(attrs={
                'class': 'toggle',
            }),
            'show_tax_breakdown': forms.CheckboxInput(attrs={
                'class': 'toggle',
            }),
            'compare_previous_period': forms.CheckboxInput(attrs={
                'class': 'toggle',
            }),
            'fiscal_year_start_month': forms.NumberInput(attrs={
                'class': 'input',
                'min': '1',
                'max': '12',
            }),
        }


class SavedReportForm(forms.ModelForm):
    """Form for creating/editing saved reports."""

    class Meta:
        model = SavedReport
        fields = [
            'name',
            'description',
            'report_type',
            'is_shared',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': _('Report name'),
            }),
            'description': forms.Textarea(attrs={
                'class': 'textarea',
                'rows': '3',
                'placeholder': _('Optional description...'),
            }),
            'report_type': forms.Select(attrs={
                'class': 'select',
            }),
            'is_shared': forms.CheckboxInput(attrs={
                'class': 'toggle',
            }),
        }
