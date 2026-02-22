"""
Pytest fixtures for analytics module tests.
"""
import os
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone


os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'


@pytest.fixture
def client():
    """Django test client."""
    return Client()


@pytest.fixture
def hub_config(db):
    """HubConfig instance for testing."""
    from apps.configuration.models import HubConfig

    config = HubConfig.get_solo()
    config.currency = 'EUR'
    config.os_language = 'en'
    config.save()
    return config


@pytest.fixture
def store_config(db):
    """StoreConfig instance for testing."""
    from apps.configuration.models import StoreConfig

    config = StoreConfig.get_solo()
    config.business_name = 'Test Store'
    config.business_address = '123 Test Street'
    config.vat_number = 'ES12345678A'
    config.tax_rate = Decimal('21.00')
    config.tax_included = True
    config.is_configured = True
    config.save()
    return config


@pytest.fixture
def authenticated_client(db, client, store_config):
    """Client with authenticated session and configured store."""
    from apps.accounts.models import LocalUser

    user = LocalUser.objects.create(
        name='Test User',
        email='test@example.com',
        role='admin',
        pin_hash='',
        is_active=True,
    )
    user.set_pin('1234')

    session = client.session
    session['local_user_id'] = str(user.id)
    session['user_name'] = user.name
    session['user_email'] = user.email
    session['user_role'] = user.role
    session['store_config_checked'] = True
    session.save()

    return client


@pytest.fixture
def hub_id(hub_config):
    """Return the hub_id from HubConfig."""
    return hub_config.hub_id


@pytest.fixture
def analytics_settings(db, hub_id):
    """AnalyticsSettings instance for testing."""
    from analytics.models import AnalyticsSettings

    return AnalyticsSettings.get_settings(hub_id)


@pytest.fixture
def saved_report(db, hub_id):
    """SavedReport instance for testing."""
    from analytics.models import SavedReport

    return SavedReport.objects.create(
        hub_id=hub_id,
        name='Test Monthly Sales',
        description='Monthly sales overview report',
        report_type='sales',
        config={
            'period': 'month',
            'columns': ['date', 'revenue', 'count'],
            'group_by': 'day',
        },
        is_shared=True,
    )


@pytest.fixture
def report_snapshot(db, hub_id):
    """ReportSnapshot instance for testing."""
    from analytics.models import ReportSnapshot

    today = timezone.now().date()
    start = today.replace(day=1)

    return ReportSnapshot.objects.create(
        hub_id=hub_id,
        report_type='sales',
        period_start=start,
        period_end=today,
        data={
            'total_revenue': 15000.00,
            'total_sales': 150,
            'avg_ticket': 100.00,
        },
    )
