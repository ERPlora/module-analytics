"""
AI context for the Analytics module.
Loaded into the assistant system prompt when this module's tools are active.
"""

CONTEXT = """
## Module Knowledge: Analytics

### Models

**AnalyticsSettings** — singleton per hub with report display preferences.
- `default_period` (choice): today, week, month, quarter, year (default: month)
- `default_currency` (str, 3 chars, default: EUR)
- `show_profit` (bool, default True): include profit/margin columns in reports
- `show_tax_breakdown` (bool, default False): show tax detail rows
- `compare_previous_period` (bool, default True): show delta vs prior period
- `fiscal_year_start_month` (int 1-12, default 1): January = fiscal year start
- Accessed via: `AnalyticsSettings.get_settings(hub_id)`

**SavedReport** — user-saved report configuration for quick re-running.
- `name` (str): report label
- `description` (text)
- `report_type` (choice): sales, products, customers, custom
- `config` (JSON dict): filters, columns, grouping options for the report engine
- `created_by_employee` (FK → accounts.LocalUser, nullable)
- `is_shared` (bool, default False): if True, visible to all employees
- `last_run_at` (datetime, nullable)

**ReportSnapshot** — cached pre-computed report data.
- `report_type` (str): type identifier matching the analytics engine
- `period_start` / `period_end` (date): date range covered
- `data` (JSON dict): full computed result set
- `generated_at` (datetime, auto)
- `is_stale` (bool, default False): set True when underlying data changes; triggers recompute

### Key flows

1. **Configure analytics**: update AnalyticsSettings singleton.
2. **Save a report**: create SavedReport with report_type and config JSON describing filters/grouping.
3. **Share a report**: set is_shared=True so all employees see it.
4. **Cache report data**: create a ReportSnapshot with period dates and computed data. Mark is_stale=True when source data changes.
5. **Load a snapshot**: query ReportSnapshot by report_type + period_start/end + is_stale=False.

### Relationships
- SavedReport.created_by_employee → accounts.LocalUser
"""
