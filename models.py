from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _

from apps.core.models import HubBaseModel


# ---------------------------------------------------------------------------
# Analytics Settings
# ---------------------------------------------------------------------------

class AnalyticsSettings(HubBaseModel):
    """Per-hub analytics configuration."""

    PERIOD_CHOICES = [
        ('today', _('Today')),
        ('week', _('This Week')),
        ('month', _('This Month')),
        ('quarter', _('This Quarter')),
        ('year', _('This Year')),
    ]

    default_period = models.CharField(
        _('Default Period'),
        max_length=10,
        choices=PERIOD_CHOICES,
        default='month',
        help_text=_('Default time period for reports.'),
    )
    default_currency = models.CharField(
        _('Default Currency'),
        max_length=3,
        default='EUR',
        help_text=_('Currency code for report display.'),
    )
    show_profit = models.BooleanField(
        _('Show Profit'),
        default=True,
        help_text=_('Show profit/margin data in reports.'),
    )
    show_tax_breakdown = models.BooleanField(
        _('Show Tax Breakdown'),
        default=False,
        help_text=_('Show detailed tax breakdown in reports.'),
    )
    compare_previous_period = models.BooleanField(
        _('Compare Previous Period'),
        default=True,
        help_text=_('Show comparison with previous period.'),
    )
    fiscal_year_start_month = models.IntegerField(
        _('Fiscal Year Start Month'),
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text=_('Month when the fiscal year starts (1=January, 12=December).'),
    )

    class Meta(HubBaseModel.Meta):
        db_table = 'analytics_settings'
        verbose_name = _('Analytics Settings')
        verbose_name_plural = _('Analytics Settings')
        unique_together = [('hub_id',)]

    def __str__(self):
        return f"Analytics Settings (hub {self.hub_id})"

    @classmethod
    def get_settings(cls, hub_id):
        """Get or create analytics settings for a hub."""
        settings, _ = cls.all_objects.get_or_create(hub_id=hub_id)
        return settings


# ---------------------------------------------------------------------------
# Saved Report
# ---------------------------------------------------------------------------

class SavedReport(HubBaseModel):
    """User-saved report configurations."""

    REPORT_TYPE_CHOICES = [
        ('sales', _('Sales')),
        ('products', _('Products')),
        ('customers', _('Customers')),
        ('custom', _('Custom')),
    ]

    name = models.CharField(
        _('Name'),
        max_length=200,
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        default='',
    )
    report_type = models.CharField(
        _('Report Type'),
        max_length=20,
        choices=REPORT_TYPE_CHOICES,
        default='sales',
    )
    config = models.JSONField(
        _('Configuration'),
        default=dict,
        help_text=_('Report configuration: filters, columns, grouping'),
    )
    created_by_employee = models.ForeignKey(
        'accounts.LocalUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='saved_reports',
        verbose_name=_('Created By'),
    )
    is_shared = models.BooleanField(
        _('Shared'),
        default=False,
        help_text=_('Make this report visible to all employees.'),
    )
    last_run_at = models.DateTimeField(
        _('Last Run'),
        null=True,
        blank=True,
    )

    class Meta(HubBaseModel.Meta):
        db_table = 'analytics_saved_report'
        verbose_name = _('Saved Report')
        verbose_name_plural = _('Saved Reports')
        ordering = ['-updated_at']

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Report Snapshot
# ---------------------------------------------------------------------------

class ReportSnapshot(HubBaseModel):
    """Cached report data for performance."""

    report_type = models.CharField(
        _('Report Type'),
        max_length=50,
    )
    period_start = models.DateField(
        _('Period Start'),
    )
    period_end = models.DateField(
        _('Period End'),
    )
    data = models.JSONField(
        _('Data'),
        default=dict,
    )
    generated_at = models.DateTimeField(
        _('Generated At'),
        auto_now_add=True,
    )
    is_stale = models.BooleanField(
        _('Is Stale'),
        default=False,
    )

    class Meta(HubBaseModel.Meta):
        db_table = 'analytics_snapshot'
        verbose_name = _('Report Snapshot')
        verbose_name_plural = _('Report Snapshots')
        indexes = [
            models.Index(
                fields=['hub_id', 'report_type', 'period_start', 'period_end'],
                name='analytics_snap_hub_type_period',
            ),
        ]

    def __str__(self):
        return f"{self.report_type} ({self.period_start} - {self.period_end})"
