# Analytics

## Overview

| Property | Value |
|----------|-------|
| **Module ID** | `analytics` |
| **Version** | `2.0.0` |
| **Icon** | `analytics-outline` |
| **Dependencies** | None |

## Models

### `AnalyticsSettings`

Per-hub analytics configuration.

| Field | Type | Details |
|-------|------|---------|
| `default_period` | CharField | max_length=10, choices: today, week, month, quarter, year |
| `default_currency` | CharField | max_length=3 |
| `show_profit` | BooleanField |  |
| `show_tax_breakdown` | BooleanField |  |
| `compare_previous_period` | BooleanField |  |
| `fiscal_year_start_month` | IntegerField |  |

**Methods:**

- `get_settings()` — Get or create analytics settings for a hub.

### `SavedReport`

User-saved report configurations.

| Field | Type | Details |
|-------|------|---------|
| `name` | CharField | max_length=200 |
| `description` | TextField | optional |
| `report_type` | CharField | max_length=20, choices: sales, products, customers, custom |
| `config` | JSONField |  |
| `created_by_employee` | ForeignKey | → `accounts.LocalUser`, on_delete=SET_NULL, optional |
| `is_shared` | BooleanField |  |
| `last_run_at` | DateTimeField | optional |

### `ReportSnapshot`

Cached report data for performance.

| Field | Type | Details |
|-------|------|---------|
| `report_type` | CharField | max_length=50 |
| `period_start` | DateField |  |
| `period_end` | DateField |  |
| `data` | JSONField |  |
| `generated_at` | DateTimeField | optional |
| `is_stale` | BooleanField |  |

## Cross-Module Relationships

| From | Field | To | on_delete | Nullable |
|------|-------|----|-----------|----------|
| `SavedReport` | `created_by_employee` | `accounts.LocalUser` | SET_NULL | Yes |

## URL Endpoints

Base path: `/m/analytics/`

| Path | Name | Method |
|------|------|--------|
| `(root)` | `dashboard` | GET |
| `sales_report/` | `sales_report` | GET |
| `products_report/` | `products_report` | GET |
| `customers_report/` | `customers_report` | GET |
| `pipeline_report/` | `pipeline_report` | GET |
| `loyalty_report/` | `loyalty_report` | GET |
| `sales/` | `sales_report` | GET |
| `products/` | `products_report` | GET |
| `customers/` | `customers_report` | GET |
| `pipeline/` | `pipeline_report` | GET |
| `loyalty/` | `loyalty_report` | GET |
| `api/chart-data/` | `api_chart_data` | GET |
| `api/export/` | `export_csv` | GET |
| `settings/` | `settings` | GET |
| `settings/save/` | `settings_save` | GET/POST |

## Permissions

| Permission | Description |
|------------|-------------|
| `analytics.view_dashboard` | View Dashboard |
| `analytics.view_sales_report` | View Sales Report |
| `analytics.view_products_report` | View Products Report |
| `analytics.view_customers_report` | View Customers Report |
| `analytics.export_reports` | Export Reports |
| `analytics.view_pipeline_report` | View Pipeline Report |
| `analytics.view_loyalty_report` | View Loyalty Report |
| `analytics.manage_settings` | Manage Settings |

**Role assignments:**

- **admin**: All permissions
- **manager**: `export_reports`, `view_customers_report`, `view_dashboard`, `view_loyalty_report`, `view_pipeline_report`, `view_products_report`, `view_sales_report`
- **employee**: `view_customers_report`, `view_dashboard`, `view_loyalty_report`, `view_pipeline_report`, `view_products_report`, `view_sales_report`

## Navigation

| View | Icon | ID | Fullpage |
|------|------|----|----------|
| Dashboard | `speedometer-outline` | `dashboard` | No |
| Sales | `trending-up-outline` | `sales_report` | No |
| Products | `cube-outline` | `products_report` | No |
| Customers | `people-outline` | `customers_report` | No |
| Pipeline | `funnel-outline` | `pipeline_report` | No |
| Loyalty | `heart-outline` | `loyalty_report` | No |
| Settings | `settings-outline` | `settings` | No |

## AI Tools

Tools available for the AI assistant:

### `list_saved_reports`

List saved analytics reports.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `report_type` | string | No | sales, products, customers, custom |
| `is_shared` | boolean | No |  |

### `get_analytics_settings`

Get analytics settings (default period, fiscal year, etc.).

### `update_analytics_settings`

Update analytics settings.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `default_period` | string | No |  |
| `fiscal_year_start_month` | integer | No |  |
| `show_profit` | boolean | No |  |
| `show_tax_breakdown` | boolean | No |  |
| `compare_previous_period` | boolean | No |  |

## File Structure

```
README.md
__init__.py
ai_tools.py
forms.py
locale/
  es/
    LC_MESSAGES/
migrations/
  0001_initial.py
  __init__.py
models.py
module.py
templates/
  analytics/
    pages/
      customers_report.html
      index.html
      loyalty_report.html
      pipeline_report.html
      products_report.html
      sales_report.html
      settings.html
    partials/
      content.html
      customers_content.html
      loyalty_content.html
      pipeline_content.html
      products_content.html
      sales_content.html
      settings_content.html
tests/
  __init__.py
  conftest.py
  test_models.py
  test_views.py
urls.py
views.py
```
