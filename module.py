from django.utils.translation import gettext_lazy as _

MODULE_ID = 'analytics'
MODULE_NAME = _('Analytics')
MODULE_VERSION = '2.0.0'
MODULE_ICON = 'analytics-outline'
MODULE_DESCRIPTION = _('Business intelligence dashboards and cross-module analytics')
MODULE_AUTHOR = 'ERPlora'
MODULE_CATEGORY = 'analytics'

MENU = {
    'label': _('Analytics'),
    'icon': 'analytics-outline',
    'order': 85,
}

NAVIGATION = [
    {'label': _('Dashboard'), 'icon': 'speedometer-outline', 'id': 'dashboard'},
    {'label': _('Sales'), 'icon': 'trending-up-outline', 'id': 'sales_report'},
    {'label': _('Products'), 'icon': 'cube-outline', 'id': 'products_report'},
    {'label': _('Customers'), 'icon': 'people-outline', 'id': 'customers_report'},
    {'label': _('Pipeline'), 'icon': 'funnel-outline', 'id': 'pipeline_report'},
    {'label': _('Loyalty'), 'icon': 'heart-outline', 'id': 'loyalty_report'},
    {'label': _('Settings'), 'icon': 'settings-outline', 'id': 'settings'},
]

DEPENDENCIES = []

PERMISSIONS = [
    'analytics.view_dashboard',
    'analytics.view_sales_report',
    'analytics.view_products_report',
    'analytics.view_customers_report',
    'analytics.export_reports',
    'analytics.view_pipeline_report',
    'analytics.view_loyalty_report',
    'analytics.manage_settings',
]
