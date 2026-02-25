# Analytics Module

Business intelligence dashboards and cross-module analytics.

## Features

- Sales, products, customers, pipeline, and loyalty reports
- Configurable default reporting period (today, week, month, quarter, year)
- Previous period comparison
- Save and share custom report configurations
- Report snapshots for cached performance data
- Configurable fiscal year start month
- Currency and tax breakdown display options
- Export report data

## Installation

This module is installed automatically via the ERPlora Marketplace.

## Configuration

Access settings via: **Menu > Analytics > Settings**

Configure default period, currency, profit visibility, tax breakdown, period comparison, and fiscal year start month.

## Usage

Access via: **Menu > Analytics**

### Views

| View | URL | Description |
|------|-----|-------------|
| Dashboard | `/m/analytics/dashboard/` | Overview of key business metrics |
| Sales | `/m/analytics/sales_report/` | Sales performance analytics |
| Products | `/m/analytics/products_report/` | Product performance analytics |
| Customers | `/m/analytics/customers_report/` | Customer behavior and segmentation analytics |
| Pipeline | `/m/analytics/pipeline_report/` | Sales pipeline and funnel analytics |
| Loyalty | `/m/analytics/loyalty_report/` | Loyalty program performance analytics |
| Settings | `/m/analytics/settings/` | Module configuration |

## Models

| Model | Description |
|-------|-------------|
| `AnalyticsSettings` | Per-hub analytics configuration (period, currency, display options, fiscal year) |
| `SavedReport` | User-saved report with name, type, JSON configuration, and sharing options |
| `ReportSnapshot` | Cached report data for a specific type and date range |

## Permissions

| Permission | Description |
|------------|-------------|
| `analytics.view_dashboard` | View the analytics dashboard |
| `analytics.view_sales_report` | View sales reports |
| `analytics.view_products_report` | View product reports |
| `analytics.view_customers_report` | View customer reports |
| `analytics.view_pipeline_report` | View pipeline reports |
| `analytics.view_loyalty_report` | View loyalty reports |
| `analytics.export_reports` | Export report data |
| `analytics.manage_settings` | Manage module settings |

## License

MIT

## Author

ERPlora Team - support@erplora.com
