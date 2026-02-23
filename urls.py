from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Reports
    path('sales/', views.sales_report, name='sales_report'),
    path('products/', views.products_report, name='products_report'),
    path('customers/', views.customers_report, name='customers_report'),
    path('pipeline/', views.pipeline_report, name='pipeline_report'),
    path('loyalty/', views.loyalty_report, name='loyalty_report'),

    # API
    path('api/chart-data/', views.api_chart_data, name='api_chart_data'),
    path('api/export/', views.export_csv, name='export_csv'),

    # Settings
    path('settings/', views.settings_view, name='settings'),
    path('settings/save/', views.settings_save, name='settings_save'),
]
