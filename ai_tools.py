"""AI tools for the Analytics module."""
from assistant.tools import AssistantTool, register_tool


@register_tool
class ListSavedReports(AssistantTool):
    name = "list_saved_reports"
    description = "List saved analytics reports."
    module_id = "analytics"
    required_permission = "analytics.view_savedreport"
    parameters = {
        "type": "object",
        "properties": {"report_type": {"type": "string", "description": "sales, products, customers, custom"}, "is_shared": {"type": "boolean"}},
        "required": [],
        "additionalProperties": False,
    }

    def execute(self, args, request):
        from analytics.models import SavedReport
        qs = SavedReport.objects.all()
        if args.get('report_type'):
            qs = qs.filter(report_type=args['report_type'])
        if 'is_shared' in args:
            qs = qs.filter(is_shared=args['is_shared'])
        return {"reports": [{"id": str(r.id), "name": r.name, "report_type": r.report_type, "is_shared": r.is_shared, "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None} for r in qs]}


@register_tool
class GetAnalyticsSettings(AssistantTool):
    name = "get_analytics_settings"
    description = "Get analytics settings (default period, fiscal year, etc.)."
    module_id = "analytics"
    required_permission = "analytics.view_analyticssettings"
    parameters = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}

    def execute(self, args, request):
        from analytics.models import AnalyticsSettings
        s = AnalyticsSettings.get_solo()
        return {"default_period": s.default_period, "default_currency": s.default_currency, "show_profit": s.show_profit, "show_tax_breakdown": s.show_tax_breakdown, "compare_previous_period": s.compare_previous_period, "fiscal_year_start_month": s.fiscal_year_start_month}


@register_tool
class UpdateAnalyticsSettings(AssistantTool):
    name = "update_analytics_settings"
    description = "Update analytics settings."
    module_id = "analytics"
    required_permission = "analytics.change_analyticssettings"
    requires_confirmation = True
    parameters = {
        "type": "object",
        "properties": {
            "default_period": {"type": "string"}, "fiscal_year_start_month": {"type": "integer"},
            "show_profit": {"type": "boolean"}, "show_tax_breakdown": {"type": "boolean"},
            "compare_previous_period": {"type": "boolean"},
        },
        "required": [],
        "additionalProperties": False,
    }

    def execute(self, args, request):
        from analytics.models import AnalyticsSettings
        s = AnalyticsSettings.get_solo()
        updated = []
        for field in ['default_period', 'fiscal_year_start_month', 'show_profit', 'show_tax_breakdown', 'compare_previous_period']:
            if field in args:
                setattr(s, field, args[field])
                updated.append(field)
        if updated:
            s.save()
        return {"updated_fields": updated, "success": True}
