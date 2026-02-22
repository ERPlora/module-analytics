"""
Tests for analytics module models.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone


pytestmark = pytest.mark.django_db


class TestAnalyticsSettings:
    """Tests for AnalyticsSettings model."""

    def test_get_settings_creates_default(self, hub_id):
        """get_settings should create a new settings record if none exists."""
        from analytics.models import AnalyticsSettings

        settings = AnalyticsSettings.get_settings(hub_id)
        assert settings is not None
        assert settings.default_period == 'month'
        assert settings.default_currency == 'EUR'
        assert settings.show_profit is True
        assert settings.show_tax_breakdown is False
        assert settings.compare_previous_period is True
        assert settings.fiscal_year_start_month == 1

    def test_get_settings_singleton_per_hub(self, hub_id):
        """get_settings should return the same record for the same hub_id."""
        from analytics.models import AnalyticsSettings

        settings1 = AnalyticsSettings.get_settings(hub_id)
        settings2 = AnalyticsSettings.get_settings(hub_id)
        assert settings1.pk == settings2.pk

    def test_get_settings_different_hubs(self, db):
        """Different hub_ids should get different settings."""
        from analytics.models import AnalyticsSettings

        hub1 = uuid.uuid4()
        hub2 = uuid.uuid4()

        settings1 = AnalyticsSettings.get_settings(hub1)
        settings2 = AnalyticsSettings.get_settings(hub2)
        assert settings1.pk != settings2.pk

    def test_settings_str(self, analytics_settings):
        """__str__ should return a descriptive string."""
        result = str(analytics_settings)
        assert 'Analytics Settings' in result

    def test_settings_update(self, analytics_settings):
        """Settings should be updatable."""
        analytics_settings.default_period = 'week'
        analytics_settings.default_currency = 'USD'
        analytics_settings.show_profit = False
        analytics_settings.save()

        analytics_settings.refresh_from_db()
        assert analytics_settings.default_period == 'week'
        assert analytics_settings.default_currency == 'USD'
        assert analytics_settings.show_profit is False


class TestSavedReport:
    """Tests for SavedReport model."""

    def test_create_saved_report(self, saved_report):
        """Should create a SavedReport with valid data."""
        assert saved_report.name == 'Test Monthly Sales'
        assert saved_report.report_type == 'sales'
        assert saved_report.is_shared is True
        assert saved_report.config['period'] == 'month'

    def test_saved_report_str(self, saved_report):
        """__str__ should return the report name."""
        assert str(saved_report) == 'Test Monthly Sales'

    def test_saved_report_default_values(self, hub_id):
        """Default values should be properly set."""
        from analytics.models import SavedReport

        report = SavedReport.objects.create(
            hub_id=hub_id,
            name='Quick Report',
        )
        assert report.report_type == 'sales'
        assert report.is_shared is False
        assert report.config == {}
        assert report.description == ''
        assert report.last_run_at is None

    def test_saved_report_soft_delete(self, saved_report):
        """Soft delete should mark is_deleted but not remove."""
        from analytics.models import SavedReport

        pk = saved_report.pk
        saved_report.delete()

        # Should not appear in default queryset
        assert SavedReport.objects.filter(pk=pk).count() == 0
        # Should appear in all_objects
        assert SavedReport.all_objects.filter(pk=pk).count() == 1

    def test_saved_report_ordering(self, hub_id):
        """Reports should be ordered by -updated_at."""
        from analytics.models import SavedReport

        r1 = SavedReport.objects.create(hub_id=hub_id, name='Report 1')
        r2 = SavedReport.objects.create(hub_id=hub_id, name='Report 2')

        # r2 was created last so should be first
        reports = list(SavedReport.objects.filter(hub_id=hub_id))
        assert reports[0].name == 'Report 2'

    def test_saved_report_with_employee(self, hub_id, authenticated_client):
        """Should accept a FK to LocalUser."""
        from analytics.models import SavedReport
        from apps.accounts.models import LocalUser

        user = LocalUser.objects.first()
        report = SavedReport.objects.create(
            hub_id=hub_id,
            name='Employee Report',
            created_by_employee=user,
        )
        assert report.created_by_employee == user


class TestReportSnapshot:
    """Tests for ReportSnapshot model."""

    def test_create_snapshot(self, report_snapshot):
        """Should create a ReportSnapshot with valid data."""
        assert report_snapshot.report_type == 'sales'
        assert report_snapshot.data['total_revenue'] == 15000.00
        assert report_snapshot.is_stale is False

    def test_snapshot_str(self, report_snapshot):
        """__str__ should show type and period."""
        result = str(report_snapshot)
        assert 'sales' in result

    def test_snapshot_generated_at(self, report_snapshot):
        """generated_at should be set automatically."""
        assert report_snapshot.generated_at is not None

    def test_snapshot_mark_stale(self, report_snapshot):
        """Should be able to mark a snapshot as stale."""
        report_snapshot.is_stale = True
        report_snapshot.save()
        report_snapshot.refresh_from_db()
        assert report_snapshot.is_stale is True


class TestDateRangeHelper:
    """Tests for the _get_date_range helper function."""

    def test_today_range(self):
        """'today' should return today, today."""
        from analytics.views import _get_date_range
        start, end = _get_date_range('today')
        today = timezone.now().date()
        assert start == today
        assert end == today

    def test_week_range(self):
        """'week' should start from Monday of current week."""
        from analytics.views import _get_date_range
        start, end = _get_date_range('week')
        today = timezone.now().date()
        assert end == today
        assert start.weekday() == 0  # Monday

    def test_month_range(self):
        """'month' should start from first day of current month."""
        from analytics.views import _get_date_range
        start, end = _get_date_range('month')
        today = timezone.now().date()
        assert end == today
        assert start.day == 1
        assert start.month == today.month

    def test_quarter_range(self):
        """'quarter' should start from first day of current quarter."""
        from analytics.views import _get_date_range
        start, end = _get_date_range('quarter')
        today = timezone.now().date()
        assert end == today
        assert start.day == 1
        assert start.month in [1, 4, 7, 10]

    def test_year_range(self):
        """'year' should start from January 1st."""
        from analytics.views import _get_date_range
        start, end = _get_date_range('year')
        today = timezone.now().date()
        assert end == today
        assert start.month == 1
        assert start.day == 1

    def test_default_range(self):
        """Unknown period should default to month."""
        from analytics.views import _get_date_range
        start, end = _get_date_range('unknown')
        today = timezone.now().date()
        assert end == today
        assert start.day == 1
