"""
Tests for analytics module views.
"""
import pytest
from django.urls import reverse


pytestmark = pytest.mark.django_db


class TestDashboardView:
    """Tests for the dashboard view."""

    def test_dashboard_loads(self, authenticated_client):
        """Dashboard page should load successfully."""
        response = authenticated_client.get(reverse('analytics:dashboard'))
        assert response.status_code == 200

    def test_dashboard_with_period(self, authenticated_client):
        """Dashboard should accept period parameter."""
        response = authenticated_client.get(
            reverse('analytics:dashboard') + '?period=week'
        )
        assert response.status_code == 200

    def test_dashboard_htmx_partial(self, authenticated_client):
        """HTMX request should return partial content."""
        response = authenticated_client.get(
            reverse('analytics:dashboard'),
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 200

    def test_dashboard_context_has_kpis(self, authenticated_client):
        """Dashboard context should contain KPI data."""
        response = authenticated_client.get(reverse('analytics:dashboard'))
        assert response.status_code == 200


class TestSalesReportView:
    """Tests for the sales report view."""

    def test_sales_report_loads(self, authenticated_client):
        """Sales report page should load successfully."""
        response = authenticated_client.get(reverse('analytics:sales_report'))
        assert response.status_code == 200

    def test_sales_report_with_period(self, authenticated_client):
        """Sales report should accept period parameter."""
        response = authenticated_client.get(
            reverse('analytics:sales_report') + '?period=year'
        )
        assert response.status_code == 200

    def test_sales_report_htmx(self, authenticated_client):
        """HTMX request should return partial content."""
        response = authenticated_client.get(
            reverse('analytics:sales_report'),
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 200


class TestProductsReportView:
    """Tests for the products report view."""

    def test_products_report_loads(self, authenticated_client):
        """Products report page should load successfully."""
        response = authenticated_client.get(reverse('analytics:products_report'))
        assert response.status_code == 200

    def test_products_report_with_period(self, authenticated_client):
        """Products report should accept period parameter."""
        response = authenticated_client.get(
            reverse('analytics:products_report') + '?period=quarter'
        )
        assert response.status_code == 200

    def test_products_report_htmx(self, authenticated_client):
        """HTMX request should return partial content."""
        response = authenticated_client.get(
            reverse('analytics:products_report'),
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 200


class TestCustomersReportView:
    """Tests for the customers report view."""

    def test_customers_report_loads(self, authenticated_client):
        """Customers report page should load successfully."""
        response = authenticated_client.get(reverse('analytics:customers_report'))
        assert response.status_code == 200

    def test_customers_report_with_period(self, authenticated_client):
        """Customers report should accept period parameter."""
        response = authenticated_client.get(
            reverse('analytics:customers_report') + '?period=today'
        )
        assert response.status_code == 200

    def test_customers_report_htmx(self, authenticated_client):
        """HTMX request should return partial content."""
        response = authenticated_client.get(
            reverse('analytics:customers_report'),
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 200


class TestChartDataAPI:
    """Tests for the chart data API endpoint."""

    def test_chart_data_revenue(self, authenticated_client):
        """Revenue chart data should return JSON."""
        response = authenticated_client.get(
            reverse('analytics:api_chart_data') + '?type=revenue&period=month'
        )
        assert response.status_code == 200
        data = response.json()
        assert 'labels' in data
        assert 'values' in data
        assert data['type'] == 'revenue'

    def test_chart_data_sales_count(self, authenticated_client):
        """Sales count chart data should return JSON."""
        response = authenticated_client.get(
            reverse('analytics:api_chart_data') + '?type=sales_count&period=week'
        )
        assert response.status_code == 200
        data = response.json()
        assert data['type'] == 'sales_count'

    def test_chart_data_customers(self, authenticated_client):
        """Customers chart data should return JSON."""
        response = authenticated_client.get(
            reverse('analytics:api_chart_data') + '?type=customers&period=month'
        )
        assert response.status_code == 200
        data = response.json()
        assert data['type'] == 'customers'

    def test_chart_data_products(self, authenticated_client):
        """Products chart data should return JSON."""
        response = authenticated_client.get(
            reverse('analytics:api_chart_data') + '?type=products&period=month'
        )
        assert response.status_code == 200
        data = response.json()
        assert data['type'] == 'products'

    def test_chart_data_default_params(self, authenticated_client):
        """Default params should work."""
        response = authenticated_client.get(reverse('analytics:api_chart_data'))
        assert response.status_code == 200
        data = response.json()
        assert data['type'] == 'revenue'
        assert data['period'] == 'month'


class TestExportCSV:
    """Tests for the CSV export endpoint."""

    def test_export_sales_csv(self, authenticated_client):
        """Sales CSV export should return a CSV file."""
        response = authenticated_client.get(
            reverse('analytics:export_csv') + '?type=sales&period=month'
        )
        assert response.status_code == 200
        assert response['Content-Type'] == 'text/csv'
        assert 'attachment' in response['Content-Disposition']
        assert 'sales' in response['Content-Disposition']

    def test_export_products_csv(self, authenticated_client):
        """Products CSV export should return a CSV file."""
        response = authenticated_client.get(
            reverse('analytics:export_csv') + '?type=products&period=month'
        )
        assert response.status_code == 200
        assert response['Content-Type'] == 'text/csv'
        assert 'products' in response['Content-Disposition']

    def test_export_customers_csv(self, authenticated_client):
        """Customers CSV export should return a CSV file."""
        response = authenticated_client.get(
            reverse('analytics:export_csv') + '?type=customers&period=month'
        )
        assert response.status_code == 200
        assert response['Content-Type'] == 'text/csv'
        assert 'customers' in response['Content-Disposition']


class TestSettingsView:
    """Tests for the settings views."""

    def test_settings_view_loads(self, authenticated_client):
        """Settings page should load successfully."""
        response = authenticated_client.get(reverse('analytics:settings'))
        assert response.status_code == 200

    def test_settings_view_htmx(self, authenticated_client):
        """HTMX request should return partial content."""
        response = authenticated_client.get(
            reverse('analytics:settings'),
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 200

    def test_settings_save(self, authenticated_client):
        """POST to settings save should update settings."""
        response = authenticated_client.post(
            reverse('analytics:settings_save'),
            {
                'default_period': 'week',
                'default_currency': 'USD',
                'show_profit': True,
                'show_tax_breakdown': True,
                'compare_previous_period': False,
                'fiscal_year_start_month': 4,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

    def test_settings_save_invalid(self, authenticated_client):
        """Invalid data should return errors."""
        response = authenticated_client.post(
            reverse('analytics:settings_save'),
            {
                'default_period': 'invalid_period',
                'fiscal_year_start_month': 13,
            },
        )
        assert response.status_code == 400


class TestAuthRequired:
    """Tests for authentication requirement."""

    def test_dashboard_requires_auth(self, client):
        """Unauthenticated users should be redirected."""
        response = client.get(reverse('analytics:dashboard'))
        assert response.status_code in [302, 403]

    def test_api_requires_auth(self, client):
        """API endpoints should require authentication."""
        response = client.get(reverse('analytics:api_chart_data'))
        assert response.status_code in [302, 403]

    def test_export_requires_auth(self, client):
        """Export should require authentication."""
        response = client.get(reverse('analytics:export_csv'))
        assert response.status_code in [302, 403]
