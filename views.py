import csv
from datetime import timedelta
from decimal import Decimal

from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import login_required, permission_required
from apps.core.htmx import htmx_view
from apps.modules_runtime.navigation import with_module_nav

from .models import AnalyticsSettings, SavedReport, ReportSnapshot
from .forms import AnalyticsSettingsForm, SavedReportForm


# ============================================================================
# Helpers
# ============================================================================

def _hub_id(request):
    return request.session.get('hub_id')


def _employee(request):
    """Return the current LocalUser from session."""
    from apps.accounts.models import LocalUser
    uid = request.session.get('local_user_id')
    if uid:
        try:
            return LocalUser.objects.get(pk=uid)
        except LocalUser.DoesNotExist:
            pass
    return None


def _get_date_range(period):
    """Return (start_date, end_date) for the given period string."""
    today = timezone.now().date()

    if period == 'today':
        return today, today
    elif period == 'week':
        start = today - timedelta(days=today.weekday())
        return start, today
    elif period == 'month':
        start = today.replace(day=1)
        return start, today
    elif period == 'quarter':
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        start = today.replace(month=quarter_month, day=1)
        return start, today
    elif period == 'year':
        start = today.replace(month=1, day=1)
        return start, today
    else:
        # Default to month
        start = today.replace(day=1)
        return start, today


def _get_previous_date_range(start_date, end_date):
    """Return the equivalent previous period for comparison."""
    delta = end_date - start_date
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - delta
    return prev_start, prev_end


# ============================================================================
# Dashboard
# ============================================================================

@require_http_methods(["GET"])
@login_required
@with_module_nav('analytics', 'dashboard')
@htmx_view('analytics/pages/index.html', 'analytics/partials/content.html')
def dashboard(request):
    hub = _hub_id(request)
    settings = AnalyticsSettings.get_settings(hub)
    period = request.GET.get('period', settings.default_period)
    start_date, end_date = _get_date_range(period)

    # Initialize KPIs
    total_revenue = Decimal('0.00')
    total_sales = 0
    avg_ticket = Decimal('0.00')
    top_products = []
    new_customers = 0
    low_stock_count = 0

    # Previous period for comparison
    prev_start, prev_end = _get_previous_date_range(start_date, end_date)
    prev_revenue = Decimal('0.00')
    prev_sales = 0

    # --- Sales data ---
    try:
        from sales.models import Sale
        from django.db.models import Sum, Count

        base_qs = Sale.objects.filter(
            hub_id=hub, is_deleted=False, status='completed',
            created_at__date__gte=start_date, created_at__date__lte=end_date,
        )
        total_sales = base_qs.count()
        agg = base_qs.aggregate(revenue=Sum('total'))
        total_revenue = agg['revenue'] or Decimal('0.00')
        avg_ticket = total_revenue / max(total_sales, 1)

        # Top products
        try:
            from sales.models import SaleItem
            top_items = (
                SaleItem.objects.filter(
                    hub_id=hub, is_deleted=False,
                    sale__status='completed',
                    sale__created_at__date__gte=start_date,
                    sale__created_at__date__lte=end_date,
                )
                .values('product_name')
                .annotate(
                    total_qty=Sum('quantity'),
                    total_revenue=Sum('line_total'),
                )
                .order_by('-total_revenue')[:5]
            )
            top_products = list(top_items)
        except Exception:
            pass

        # Previous period sales
        if settings.compare_previous_period:
            prev_qs = Sale.objects.filter(
                hub_id=hub, is_deleted=False, status='completed',
                created_at__date__gte=prev_start, created_at__date__lte=prev_end,
            )
            prev_sales = prev_qs.count()
            prev_agg = prev_qs.aggregate(revenue=Sum('total'))
            prev_revenue = prev_agg['revenue'] or Decimal('0.00')
    except ImportError:
        pass

    # --- Customers data ---
    try:
        from customers.models import Customer

        new_customers = Customer.objects.filter(
            hub_id=hub, is_deleted=False,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        ).count()
    except ImportError:
        pass

    # --- Inventory data ---
    try:
        from inventory.models import Product

        low_stock_count = Product.objects.filter(
            hub_id=hub, is_deleted=False, is_active=True,
        ).extra(
            where=['stock <= low_stock_threshold']
        ).count()
    except (ImportError, Exception):
        # Fallback without .extra()
        try:
            from inventory.models import Product
            from django.db.models import F
            low_stock_count = Product.objects.filter(
                hub_id=hub, is_deleted=False, is_active=True,
                stock__lte=F('low_stock_threshold'),
            ).count()
        except (ImportError, Exception):
            pass

    # --- Leads data (if leads module active) ---
    has_leads_module = False
    pipeline_value = Decimal('0.00')
    open_leads = 0
    try:
        from leads.models import Lead
        from django.db.models import Sum as LeadSum
        has_leads_module = True
        leads_qs = Lead.objects.filter(hub_id=hub, is_deleted=False, status='open')
        open_leads = leads_qs.count()
        agg = leads_qs.aggregate(total=LeadSum('value'))
        pipeline_value = agg['total'] or Decimal('0.00')
    except ImportError:
        pass

    # --- Support data (if support module active) ---
    has_support_module = False
    open_tickets = 0
    try:
        from support.models import Ticket
        has_support_module = True
        open_tickets = Ticket.objects.filter(
            hub_id=hub, is_deleted=False,
            status__in=['open', 'in_progress', 'waiting_customer'],
        ).count()
    except ImportError:
        pass

    # --- Feedback data (if feedback module active) ---
    has_feedback_module = False
    avg_nps = None
    try:
        from feedback.models import FeedbackResponse
        has_feedback_module = True
        nps_qs = FeedbackResponse.objects.filter(
            hub_id=hub, is_deleted=False,
            form__form_type='nps_10',
            score__isnull=False,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        if nps_qs.exists():
            promoters = nps_qs.filter(score__gte=9).count()
            detractors = nps_qs.filter(score__lte=6).count()
            total_responses = nps_qs.count()
            if total_responses > 0:
                avg_nps = round((promoters - detractors) / total_responses * 100)
    except ImportError:
        pass

    # --- Loyalty module detection ---
    has_loyalty_module = False
    try:
        from _loyalty.models import LoyaltyMember
        has_loyalty_module = True
    except ImportError:
        pass

    # --- Segments module detection ---
    has_segments_module = False
    try:
        from segments.models import Segment
        has_segments_module = True
    except ImportError:
        pass

    # Calculate percentage changes
    revenue_change = None
    sales_change = None
    if settings.compare_previous_period and prev_revenue > 0:
        revenue_change = float((total_revenue - prev_revenue) / prev_revenue * 100)
    if settings.compare_previous_period and prev_sales > 0:
        sales_change = float((total_sales - prev_sales) / prev_sales * 100)

    return {
        'settings': settings,
        'period': period,
        'start_date': start_date,
        'end_date': end_date,
        'total_revenue': total_revenue,
        'total_sales': total_sales,
        'avg_ticket': avg_ticket,
        'top_products': top_products,
        'new_customers': new_customers,
        'low_stock_count': low_stock_count,
        'revenue_change': revenue_change,
        'sales_change': sales_change,
        'prev_revenue': prev_revenue,
        'prev_sales': prev_sales,
        # CRM KPIs
        'pipeline_value': pipeline_value,
        'open_leads': open_leads,
        'open_tickets': open_tickets,
        'avg_nps': avg_nps,
        # Module availability flags
        'has_leads_module': has_leads_module,
        'has_support_module': has_support_module,
        'has_feedback_module': has_feedback_module,
        'has_loyalty_module': has_loyalty_module,
        'has_segments_module': has_segments_module,
    }


# ============================================================================
# Sales Report
# ============================================================================

@require_http_methods(["GET"])
@login_required
@with_module_nav('analytics', 'sales_report')
@htmx_view('analytics/pages/sales_report.html', 'analytics/partials/sales_content.html')
def sales_report(request):
    hub = _hub_id(request)
    settings = AnalyticsSettings.get_settings(hub)
    period = request.GET.get('period', settings.default_period)
    start_date, end_date = _get_date_range(period)

    revenue_by_day = []
    payment_breakdown = {}
    sales_by_employee = []
    hourly_distribution = []
    total_revenue = Decimal('0.00')
    total_sales = 0
    total_tax = Decimal('0.00')

    try:
        from sales.models import Sale, SaleItem, PaymentMethod
        from django.db.models import Sum, Count
        from django.db.models.functions import TruncDay, TruncHour

        base_qs = Sale.objects.filter(
            hub_id=hub, is_deleted=False, status='completed',
            created_at__date__gte=start_date, created_at__date__lte=end_date,
        )

        total_sales = base_qs.count()
        agg = base_qs.aggregate(
            revenue=Sum('total'),
            tax=Sum('tax_amount'),
        )
        total_revenue = agg['revenue'] or Decimal('0.00')
        total_tax = agg['tax'] or Decimal('0.00')

        # Revenue by day
        daily = (
            base_qs.annotate(day=TruncDay('created_at'))
            .values('day')
            .annotate(revenue=Sum('total'), count=Count('id'))
            .order_by('day')
        )
        revenue_by_day = [
            {
                'date': row['day'].strftime('%Y-%m-%d'),
                'revenue': float(row['revenue']),
                'count': row['count'],
            }
            for row in daily
        ]

        # Payment method breakdown
        for pm in PaymentMethod.objects.filter(hub_id=hub, is_deleted=False, is_active=True):
            pm_sales = base_qs.filter(payment_method=pm)
            pm_count = pm_sales.count()
            if pm_count > 0:
                pm_total = pm_sales.aggregate(s=Sum('total'))['s'] or Decimal('0.00')
                payment_breakdown[pm.name] = {
                    'count': pm_count,
                    'total': float(pm_total),
                    'percentage': round(pm_count * 100 / max(total_sales, 1)),
                }

        # Sales by employee
        emp_data = (
            base_qs.values('employee__name')
            .annotate(
                count=Count('id'),
                revenue=Sum('total'),
            )
            .order_by('-revenue')
        )
        sales_by_employee = [
            {
                'name': row['employee__name'] or _('Unknown'),
                'count': row['count'],
                'revenue': float(row['revenue']),
            }
            for row in emp_data
        ]

        # Hourly distribution
        hourly = (
            base_qs.annotate(hour=TruncHour('created_at'))
            .values('hour')
            .annotate(count=Count('id'), revenue=Sum('total'))
            .order_by('hour')
        )
        hours_data = {}
        for row in hourly:
            h = row['hour'].hour
            if h not in hours_data:
                hours_data[h] = {'count': 0, 'revenue': Decimal('0.00')}
            hours_data[h]['count'] += row['count']
            hours_data[h]['revenue'] += row['revenue']

        hourly_distribution = [
            {
                'hour': f'{h:02d}:00',
                'count': hours_data.get(h, {}).get('count', 0),
                'revenue': float(hours_data.get(h, {}).get('revenue', 0)),
            }
            for h in range(24)
        ]

    except ImportError:
        pass

    return {
        'settings': settings,
        'period': period,
        'start_date': start_date,
        'end_date': end_date,
        'total_revenue': total_revenue,
        'total_sales': total_sales,
        'total_tax': total_tax,
        'revenue_by_day': revenue_by_day,
        'payment_breakdown': payment_breakdown,
        'sales_by_employee': sales_by_employee,
        'hourly_distribution': hourly_distribution,
    }


# ============================================================================
# Products Report
# ============================================================================

@require_http_methods(["GET"])
@login_required
@with_module_nav('analytics', 'products_report')
@htmx_view('analytics/pages/products_report.html', 'analytics/partials/products_content.html')
def products_report(request):
    hub = _hub_id(request)
    settings = AnalyticsSettings.get_settings(hub)
    period = request.GET.get('period', settings.default_period)
    start_date, end_date = _get_date_range(period)

    top_sellers = []
    slow_movers = []
    stock_value = Decimal('0.00')
    total_products = 0
    low_stock_count = 0
    margin_data = []

    # --- Sales data for products ---
    try:
        from sales.models import SaleItem
        from django.db.models import Sum, Count, F

        items_qs = SaleItem.objects.filter(
            hub_id=hub, is_deleted=False,
            sale__status='completed',
            sale__created_at__date__gte=start_date,
            sale__created_at__date__lte=end_date,
        )

        # Top sellers
        top_items = (
            items_qs
            .values('product_name', 'product_sku')
            .annotate(
                total_qty=Sum('quantity'),
                total_revenue=Sum('line_total'),
            )
            .order_by('-total_revenue')[:10]
        )
        top_sellers = list(top_items)

        # Slow movers (products with sales but very low quantity)
        slow_items = (
            items_qs
            .values('product_name', 'product_sku')
            .annotate(
                total_qty=Sum('quantity'),
                total_revenue=Sum('line_total'),
            )
            .order_by('total_qty')[:10]
        )
        slow_movers = list(slow_items)

    except ImportError:
        pass

    # --- Inventory data ---
    try:
        from inventory.models import Product
        from django.db.models import F, Sum as AggSum

        products_qs = Product.objects.filter(
            hub_id=hub, is_deleted=False, is_active=True,
        )
        total_products = products_qs.count()

        # Stock value (price * stock)
        stock_agg = products_qs.aggregate(
            total_value=AggSum(F('price') * F('stock')),
        )
        stock_value = stock_agg['total_value'] or Decimal('0.00')

        # Low stock count
        low_stock_count = products_qs.filter(
            stock__lte=F('low_stock_threshold'),
        ).count()

        # Margin analysis (top products by margin)
        margin_items = products_qs.filter(
            cost__gt=0,
        ).order_by('-price')[:10]
        margin_data = [
            {
                'name': p.name,
                'sku': p.sku,
                'price': float(p.price),
                'cost': float(p.cost),
                'margin': float(p.profit_margin),
                'stock': p.stock,
            }
            for p in margin_items
        ]

    except ImportError:
        pass

    return {
        'settings': settings,
        'period': period,
        'start_date': start_date,
        'end_date': end_date,
        'top_sellers': top_sellers,
        'slow_movers': slow_movers,
        'stock_value': stock_value,
        'total_products': total_products,
        'low_stock_count': low_stock_count,
        'margin_data': margin_data,
    }


# ============================================================================
# Customers Report
# ============================================================================

@require_http_methods(["GET"])
@login_required
@with_module_nav('analytics', 'customers_report')
@htmx_view('analytics/pages/customers_report.html', 'analytics/partials/customers_content.html')
def customers_report(request):
    hub = _hub_id(request)
    settings = AnalyticsSettings.get_settings(hub)
    period = request.GET.get('period', settings.default_period)
    start_date, end_date = _get_date_range(period)

    total_customers = 0
    new_customers = 0
    returning_customers = 0
    top_spenders = []
    avg_lifetime_value = Decimal('0.00')
    visit_frequency = []
    lifecycle_distribution = []
    source_distribution = []

    try:
        from customers.models import Customer
        from django.db.models import Sum, Avg

        customers_qs = Customer.objects.filter(
            hub_id=hub, is_deleted=False,
        )
        total_customers = customers_qs.count()

        # New customers in period
        new_customers = customers_qs.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        ).count()

        # Returning customers (have made purchases before the period)
        returning_customers = customers_qs.filter(
            last_purchase_date__isnull=False,
            last_purchase_date__date__gte=start_date,
            last_purchase_date__date__lte=end_date,
            created_at__date__lt=start_date,
        ).count()

        # Top spenders
        top = customers_qs.filter(
            total_spent__gt=0,
        ).order_by('-total_spent')[:10]
        top_spenders = [
            {
                'name': c.name,
                'email': c.email,
                'total_spent': float(c.total_spent),
                'total_purchases': c.total_purchases,
                'avg_purchase': float(c.average_purchase),
            }
            for c in top
        ]

        # Average lifetime value
        avg_agg = customers_qs.filter(
            total_spent__gt=0,
        ).aggregate(avg_ltv=Avg('total_spent'))
        avg_lifetime_value = avg_agg['avg_ltv'] or Decimal('0.00')

        # Visit frequency (group customers by purchase count)
        freq_ranges = [
            ('1', 1, 1),
            ('2-5', 2, 5),
            ('6-10', 6, 10),
            ('11-20', 11, 20),
            ('20+', 21, 99999),
        ]
        for label, low, high in freq_ranges:
            count = customers_qs.filter(
                total_purchases__gte=low,
                total_purchases__lte=high,
            ).count()
            if count > 0:
                visit_frequency.append({
                    'range': label,
                    'count': count,
                })

        # Lifecycle distribution
        try:
            from customers.models import LIFECYCLE_STAGE_CHOICES
            for stage, label in LIFECYCLE_STAGE_CHOICES:
                count = customers_qs.filter(lifecycle_stage=stage).count()
                if count > 0:
                    lifecycle_distribution.append({
                        'stage': str(label),
                        'key': stage,
                        'count': count,
                    })
        except Exception:
            pass

        # Source distribution
        try:
            from customers.models import SOURCE_CHOICES
            for source, label in SOURCE_CHOICES:
                count = customers_qs.filter(source=source).count()
                if count > 0:
                    source_distribution.append({
                        'source': str(label),
                        'key': source,
                        'count': count,
                    })
        except Exception:
            pass

    except ImportError:
        pass

    return {
        'settings': settings,
        'period': period,
        'start_date': start_date,
        'end_date': end_date,
        'total_customers': total_customers,
        'new_customers': new_customers,
        'returning_customers': returning_customers,
        'top_spenders': top_spenders,
        'avg_lifetime_value': avg_lifetime_value,
        'visit_frequency': visit_frequency,
        'lifecycle_distribution': lifecycle_distribution,
        'source_distribution': source_distribution,
    }


# ============================================================================
# Pipeline Report
# ============================================================================

@require_http_methods(["GET"])
@login_required
@with_module_nav('analytics', 'pipeline_report')
@htmx_view('analytics/pages/pipeline_report.html', 'analytics/partials/pipeline_content.html')
def pipeline_report(request):
    hub = _hub_id(request)
    settings = AnalyticsSettings.get_settings(hub)
    period = request.GET.get('period', settings.default_period)
    start_date, end_date = _get_date_range(period)

    # Module availability flags
    has_leads_module = False
    has_quotes_module = False

    # Pipeline data
    pipeline_value = Decimal('0.00')
    open_leads = 0
    conversion_rate = 0
    avg_close_days = 0
    pipeline_by_stage = []
    leads_by_source = []
    loss_reasons = []
    won_lost_monthly = []

    # --- Leads data ---
    try:
        from leads.models import Lead, PipelineStage, LossReason, Pipeline
        from django.db.models import Sum, Count, Avg, F
        from django.db.models.functions import TruncMonth
        has_leads_module = True

        all_leads = Lead.objects.filter(hub_id=hub, is_deleted=False)
        open_qs = all_leads.filter(status='open')
        open_leads = open_qs.count()
        agg = open_qs.aggregate(total=Sum('value'))
        pipeline_value = agg['total'] or Decimal('0.00')

        # Conversion rate (won / total closed in period)
        period_leads = all_leads.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        closed_leads = all_leads.filter(
            status__in=['won', 'lost'],
        )
        # Filter closed leads by their won/lost date in the period
        won_in_period = all_leads.filter(
            status='won',
            won_date__date__gte=start_date,
            won_date__date__lte=end_date,
        )
        lost_in_period = all_leads.filter(
            status='lost',
            lost_date__date__gte=start_date,
            lost_date__date__lte=end_date,
        )
        total_closed_period = won_in_period.count() + lost_in_period.count()
        if total_closed_period > 0:
            conversion_rate = round(won_in_period.count() / total_closed_period * 100)

        # Average close time (won leads)
        won_leads = all_leads.filter(status='won', won_date__isnull=False)
        if won_leads.exists():
            total_days = 0
            count = 0
            for lead in won_leads[:100]:  # Limit for performance
                delta = lead.won_date - lead.created_at
                total_days += delta.days
                count += 1
            if count > 0:
                avg_close_days = round(total_days / count)

        # Pipeline by stage
        default_pipeline = Pipeline.objects.filter(
            hub_id=hub, is_deleted=False, is_default=True,
        ).first()
        if not default_pipeline:
            default_pipeline = Pipeline.objects.filter(
                hub_id=hub, is_deleted=False,
            ).first()

        if default_pipeline:
            stages = PipelineStage.objects.filter(
                hub_id=hub, is_deleted=False,
                pipeline=default_pipeline,
            ).order_by('order')
            for stage in stages:
                stage_leads = open_qs.filter(stage=stage)
                stage_count = stage_leads.count()
                stage_value = stage_leads.aggregate(
                    total=Sum('value'),
                )['total'] or Decimal('0.00')
                pipeline_by_stage.append({
                    'name': stage.name,
                    'color': stage.color,
                    'count': stage_count,
                    'value': float(stage_value),
                    'probability': stage.probability,
                })

        # Leads by source
        source_data = (
            all_leads.filter(status='open')
            .values('source')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        from leads.models import SOURCE_CHOICES as LEAD_SOURCE_CHOICES
        source_map = dict(LEAD_SOURCE_CHOICES)
        for row in source_data:
            leads_by_source.append({
                'source': str(source_map.get(row['source'], row['source'])),
                'count': row['count'],
            })

        # Loss reasons breakdown
        loss_data = (
            all_leads.filter(
                status='lost',
                loss_reason__isnull=False,
                lost_date__date__gte=start_date,
                lost_date__date__lte=end_date,
            )
            .values('loss_reason__name')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        for row in loss_data:
            loss_reasons.append({
                'reason': row['loss_reason__name'],
                'count': row['count'],
            })

        # Won vs Lost per month (last 6 months)
        six_months_ago = (timezone.now() - timedelta(days=180)).date()

        won_monthly = (
            all_leads.filter(
                status='won',
                won_date__date__gte=six_months_ago,
            )
            .annotate(month=TruncMonth('won_date'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
        )
        lost_monthly = (
            all_leads.filter(
                status='lost',
                lost_date__date__gte=six_months_ago,
            )
            .annotate(month=TruncMonth('lost_date'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
        )

        # Merge into a dict
        monthly_data = {}
        for row in won_monthly:
            key = row['month'].strftime('%Y-%m')
            monthly_data.setdefault(key, {'month': row['month'].strftime('%b %Y'), 'won': 0, 'lost': 0})
            monthly_data[key]['won'] = row['count']
        for row in lost_monthly:
            key = row['month'].strftime('%Y-%m')
            monthly_data.setdefault(key, {'month': row['month'].strftime('%b %Y'), 'won': 0, 'lost': 0})
            monthly_data[key]['lost'] = row['count']
        won_lost_monthly = [monthly_data[k] for k in sorted(monthly_data.keys())]

    except ImportError:
        pass

    # --- Quotes data ---
    quotes_total = 0
    quotes_value = Decimal('0.00')
    quotes_accepted = 0
    quotes_acceptance_rate = 0
    try:
        from quotes.models import Quote
        from django.db.models import Sum as QSum, Count as QCount
        has_quotes_module = True

        quotes_qs = Quote.objects.filter(
            hub_id=hub, is_deleted=False,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        quotes_total = quotes_qs.count()
        q_agg = quotes_qs.aggregate(total=QSum('total'))
        quotes_value = q_agg['total'] or Decimal('0.00')
        quotes_accepted = quotes_qs.filter(status='accepted').count()
        # Acceptance rate: accepted / (accepted + rejected)
        quotes_decided = quotes_qs.filter(status__in=['accepted', 'rejected']).count()
        if quotes_decided > 0:
            quotes_acceptance_rate = round(quotes_accepted / quotes_decided * 100)
    except ImportError:
        pass

    return {
        'settings': settings,
        'period': period,
        'start_date': start_date,
        'end_date': end_date,
        # Module flags
        'has_leads_module': has_leads_module,
        'has_quotes_module': has_quotes_module,
        # Pipeline KPIs
        'pipeline_value': pipeline_value,
        'open_leads': open_leads,
        'conversion_rate': conversion_rate,
        'avg_close_days': avg_close_days,
        # Pipeline details
        'pipeline_by_stage': pipeline_by_stage,
        'leads_by_source': leads_by_source,
        'loss_reasons': loss_reasons,
        'won_lost_monthly': won_lost_monthly,
        # Quotes
        'quotes_total': quotes_total,
        'quotes_value': quotes_value,
        'quotes_accepted': quotes_accepted,
        'quotes_acceptance_rate': quotes_acceptance_rate,
    }


# ============================================================================
# Loyalty Report
# ============================================================================

@require_http_methods(["GET"])
@login_required
@with_module_nav('analytics', 'loyalty_report')
@htmx_view('analytics/pages/loyalty_report.html', 'analytics/partials/loyalty_content.html')
def loyalty_report(request):
    hub = _hub_id(request)
    settings = AnalyticsSettings.get_settings(hub)
    period = request.GET.get('period', settings.default_period)
    start_date, end_date = _get_date_range(period)

    # Module availability flags
    has_customers_module = False
    has_loyalty_module = False
    has_feedback_module = False
    has_segments_module = False

    # Customer data
    total_customers = 0
    lifecycle_distribution = []
    source_distribution = []

    # --- Customers data ---
    try:
        from customers.models import Customer, LIFECYCLE_STAGE_CHOICES, SOURCE_CHOICES
        has_customers_module = True

        customers_qs = Customer.objects.filter(hub_id=hub, is_deleted=False)
        total_customers = customers_qs.count()

        # Lifecycle distribution
        for stage, label in LIFECYCLE_STAGE_CHOICES:
            count = customers_qs.filter(lifecycle_stage=stage).count()
            if count > 0:
                lifecycle_distribution.append({
                    'stage': str(label),
                    'key': stage,
                    'count': count,
                })

        # Source distribution
        for source, label in SOURCE_CHOICES:
            count = customers_qs.filter(source=source).count()
            if count > 0:
                source_distribution.append({
                    'source': str(label),
                    'key': source,
                    'count': count,
                })
    except ImportError:
        pass

    # --- Loyalty data ---
    total_members = 0
    active_members = 0
    tier_distribution = []
    total_points_issued = 0
    total_points_redeemed = 0
    try:
        from _loyalty.models import LoyaltyMember, LoyaltyTier, PointsTransaction
        from django.db.models import Sum as LSum
        has_loyalty_module = True

        members_qs = LoyaltyMember.objects.filter(hub_id=hub, is_deleted=False)
        total_members = members_qs.count()
        active_members = members_qs.filter(is_active=True).count()

        # Tier distribution
        tiers = LoyaltyTier.objects.filter(
            hub_id=hub, is_deleted=False, is_active=True,
        ).order_by('sort_order')
        for tier in tiers:
            count = members_qs.filter(tier=tier).count()
            tier_distribution.append({
                'name': tier.name,
                'color': tier.color,
                'count': count,
            })

        # Points issued vs redeemed in period
        txn_qs = PointsTransaction.objects.filter(
            hub_id=hub, is_deleted=False,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        earn_agg = txn_qs.filter(
            transaction_type='earn',
        ).aggregate(total=LSum('points'))
        total_points_issued = earn_agg['total'] or 0

        redeem_agg = txn_qs.filter(
            transaction_type='redeem',
        ).aggregate(total=LSum('points'))
        total_points_redeemed = abs(redeem_agg['total'] or 0)
    except ImportError:
        pass

    # --- Feedback / NPS data ---
    avg_nps = None
    nps_trend = []
    try:
        from feedback.models import FeedbackResponse
        from django.db.models.functions import TruncMonth as FTruncMonth
        from django.db.models import Count as FCount
        has_feedback_module = True

        nps_qs = FeedbackResponse.objects.filter(
            hub_id=hub, is_deleted=False,
            form__form_type='nps_10',
            score__isnull=False,
        )

        # Overall NPS for the period
        period_nps = nps_qs.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        if period_nps.exists():
            promoters = period_nps.filter(score__gte=9).count()
            detractors = period_nps.filter(score__lte=6).count()
            total_responses = period_nps.count()
            if total_responses > 0:
                avg_nps = round((promoters - detractors) / total_responses * 100)

        # NPS trend (last 6 months)
        six_months_ago = (timezone.now() - timedelta(days=180)).date()
        monthly_responses = (
            nps_qs.filter(created_at__date__gte=six_months_ago)
            .annotate(month=FTruncMonth('created_at'))
            .values('month')
            .annotate(total=FCount('id'))
            .order_by('month')
        )
        for row in monthly_responses:
            month_qs = nps_qs.filter(
                created_at__year=row['month'].year,
                created_at__month=row['month'].month,
            )
            m_promoters = month_qs.filter(score__gte=9).count()
            m_detractors = month_qs.filter(score__lte=6).count()
            m_total = row['total']
            m_nps = round((m_promoters - m_detractors) / m_total * 100) if m_total > 0 else 0
            nps_trend.append({
                'month': row['month'].strftime('%b %Y'),
                'nps': m_nps,
                'responses': m_total,
            })
    except ImportError:
        pass

    # --- Segments data ---
    active_segments = []
    try:
        from segments.models import Segment
        has_segments_module = True

        segments_qs = Segment.objects.filter(
            hub_id=hub, is_deleted=False, is_active=True,
        ).order_by('-customer_count')[:10]
        active_segments = [
            {
                'name': s.name,
                'color': s.color,
                'count': s.customer_count,
                'description': s.description,
            }
            for s in segments_qs
        ]
    except ImportError:
        pass

    return {
        'settings': settings,
        'period': period,
        'start_date': start_date,
        'end_date': end_date,
        # Module flags
        'has_customers_module': has_customers_module,
        'has_loyalty_module': has_loyalty_module,
        'has_feedback_module': has_feedback_module,
        'has_segments_module': has_segments_module,
        # Customer data
        'total_customers': total_customers,
        'lifecycle_distribution': lifecycle_distribution,
        'source_distribution': source_distribution,
        # Loyalty data
        'total_members': total_members,
        'active_members': active_members,
        'tier_distribution': tier_distribution,
        'total_points_issued': total_points_issued,
        'total_points_redeemed': total_points_redeemed,
        # Feedback data
        'avg_nps': avg_nps,
        'nps_trend': nps_trend,
        # Segments
        'active_segments': active_segments,
    }


# ============================================================================
# API: Chart Data
# ============================================================================

@require_http_methods(["GET"])
@login_required
def api_chart_data(request):
    """Return JSON chart data based on ?type= and ?period= params."""
    hub = _hub_id(request)
    chart_type = request.GET.get('type', 'revenue')
    period = request.GET.get('period', 'month')
    start_date, end_date = _get_date_range(period)

    labels = []
    values = []

    if chart_type == 'revenue':
        try:
            from sales.models import Sale
            from django.db.models import Sum
            from django.db.models.functions import TruncDay

            daily = (
                Sale.objects.filter(
                    hub_id=hub, is_deleted=False, status='completed',
                    created_at__date__gte=start_date, created_at__date__lte=end_date,
                )
                .annotate(day=TruncDay('created_at'))
                .values('day')
                .annotate(total=Sum('total'))
                .order_by('day')
            )
            for row in daily:
                labels.append(row['day'].strftime('%d/%m'))
                values.append(float(row['total']))
        except ImportError:
            pass

    elif chart_type == 'sales_count':
        try:
            from sales.models import Sale
            from django.db.models import Count
            from django.db.models.functions import TruncDay

            daily = (
                Sale.objects.filter(
                    hub_id=hub, is_deleted=False, status='completed',
                    created_at__date__gte=start_date, created_at__date__lte=end_date,
                )
                .annotate(day=TruncDay('created_at'))
                .values('day')
                .annotate(count=Count('id'))
                .order_by('day')
            )
            for row in daily:
                labels.append(row['day'].strftime('%d/%m'))
                values.append(row['count'])
        except ImportError:
            pass

    elif chart_type == 'customers':
        try:
            from customers.models import Customer
            from django.db.models import Count
            from django.db.models.functions import TruncDay

            daily = (
                Customer.objects.filter(
                    hub_id=hub, is_deleted=False,
                    created_at__date__gte=start_date, created_at__date__lte=end_date,
                )
                .annotate(day=TruncDay('created_at'))
                .values('day')
                .annotate(count=Count('id'))
                .order_by('day')
            )
            for row in daily:
                labels.append(row['day'].strftime('%d/%m'))
                values.append(row['count'])
        except ImportError:
            pass

    elif chart_type == 'products':
        try:
            from sales.models import SaleItem
            from django.db.models import Sum

            items = (
                SaleItem.objects.filter(
                    hub_id=hub, is_deleted=False,
                    sale__status='completed',
                    sale__created_at__date__gte=start_date,
                    sale__created_at__date__lte=end_date,
                )
                .values('product_name')
                .annotate(total=Sum('line_total'))
                .order_by('-total')[:10]
            )
            for row in items:
                labels.append(row['product_name'] or _('Unknown'))
                values.append(float(row['total']))
        except ImportError:
            pass

    elif chart_type == 'pipeline_by_stage':
        try:
            from leads.models import Lead, PipelineStage, Pipeline
            from django.db.models import Sum, Count

            default_pipeline = Pipeline.objects.filter(
                hub_id=hub, is_deleted=False, is_default=True,
            ).first()
            if not default_pipeline:
                default_pipeline = Pipeline.objects.filter(
                    hub_id=hub, is_deleted=False,
                ).first()

            if default_pipeline:
                stages = PipelineStage.objects.filter(
                    hub_id=hub, is_deleted=False,
                    pipeline=default_pipeline,
                ).order_by('order')
                for stage in stages:
                    stage_value = Lead.objects.filter(
                        hub_id=hub, is_deleted=False,
                        status='open', stage=stage,
                    ).aggregate(total=Sum('value'))['total'] or 0
                    labels.append(stage.name)
                    values.append(float(stage_value))
        except ImportError:
            pass

    elif chart_type == 'lifecycle':
        try:
            from customers.models import Customer, LIFECYCLE_STAGE_CHOICES
            from django.db.models import Count

            customers_qs = Customer.objects.filter(hub_id=hub, is_deleted=False)
            for stage, label in LIFECYCLE_STAGE_CHOICES:
                count = customers_qs.filter(lifecycle_stage=stage).count()
                if count > 0:
                    labels.append(str(label))
                    values.append(count)
        except ImportError:
            pass

    elif chart_type == 'nps_trend':
        try:
            from feedback.models import FeedbackResponse
            from django.db.models import Count
            from django.db.models.functions import TruncMonth

            six_months_ago = (timezone.now() - timedelta(days=180)).date()
            nps_qs = FeedbackResponse.objects.filter(
                hub_id=hub, is_deleted=False,
                form__form_type='nps_10',
                score__isnull=False,
                created_at__date__gte=six_months_ago,
            )
            monthly = (
                nps_qs.annotate(month=TruncMonth('created_at'))
                .values('month')
                .annotate(total=Count('id'))
                .order_by('month')
            )
            for row in monthly:
                month_qs = nps_qs.filter(
                    created_at__year=row['month'].year,
                    created_at__month=row['month'].month,
                )
                promoters = month_qs.filter(score__gte=9).count()
                detractors = month_qs.filter(score__lte=6).count()
                m_total = row['total']
                nps = round((promoters - detractors) / m_total * 100) if m_total > 0 else 0
                labels.append(row['month'].strftime('%b %Y'))
                values.append(nps)
        except ImportError:
            pass

    return JsonResponse({
        'labels': labels,
        'values': values,
        'type': chart_type,
        'period': period,
    })


# ============================================================================
# Export CSV
# ============================================================================

@require_http_methods(["GET"])
@login_required
def export_csv(request):
    """Export current report data as CSV."""
    hub = _hub_id(request)
    report_type = request.GET.get('type', 'sales')
    period = request.GET.get('period', 'month')
    start_date, end_date = _get_date_range(period)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="analytics_{report_type}_{start_date}_{end_date}.csv"'
    writer = csv.writer(response)

    if report_type == 'sales':
        writer.writerow([
            _('Sale Number'), _('Date'), _('Employee'), _('Customer'),
            _('Payment Method'), _('Subtotal'), _('Tax'), _('Total'), _('Status'),
        ])
        try:
            from sales.models import Sale
            sales = Sale.objects.filter(
                hub_id=hub, is_deleted=False,
                created_at__date__gte=start_date, created_at__date__lte=end_date,
            ).select_related('employee', 'payment_method').order_by('-created_at')

            for sale in sales:
                writer.writerow([
                    sale.sale_number,
                    sale.created_at.strftime('%Y-%m-%d %H:%M'),
                    sale.employee.name if sale.employee else '',
                    sale.customer_name,
                    sale.payment_method_name,
                    float(sale.subtotal),
                    float(sale.tax_amount),
                    float(sale.total),
                    sale.get_status_display(),
                ])
        except ImportError:
            pass

    elif report_type == 'products':
        writer.writerow([
            _('Product'), _('SKU'), _('Quantity Sold'),
            _('Revenue'), _('Stock'), _('Price'), _('Cost'),
        ])
        try:
            from sales.models import SaleItem
            from django.db.models import Sum

            items = (
                SaleItem.objects.filter(
                    hub_id=hub, is_deleted=False,
                    sale__status='completed',
                    sale__created_at__date__gte=start_date,
                    sale__created_at__date__lte=end_date,
                )
                .values('product_name', 'product_sku')
                .annotate(
                    total_qty=Sum('quantity'),
                    total_revenue=Sum('line_total'),
                )
                .order_by('-total_revenue')
            )
            for item in items:
                writer.writerow([
                    item['product_name'],
                    item['product_sku'],
                    float(item['total_qty']),
                    float(item['total_revenue']),
                    '', '', '',
                ])
        except ImportError:
            pass

    elif report_type == 'customers':
        writer.writerow([
            _('Name'), _('Email'), _('Phone'),
            _('Total Purchases'), _('Total Spent'), _('Last Purchase'),
        ])
        try:
            from customers.models import Customer

            customers = Customer.objects.filter(
                hub_id=hub, is_deleted=False,
            ).order_by('-total_spent')

            for c in customers:
                writer.writerow([
                    c.name,
                    c.email,
                    c.phone,
                    c.total_purchases,
                    float(c.total_spent),
                    c.last_purchase_date.strftime('%Y-%m-%d') if c.last_purchase_date else '',
                ])
        except ImportError:
            pass

    return response


# ============================================================================
# Settings
# ============================================================================

@require_http_methods(["GET"])
@login_required
@permission_required('analytics.manage_settings')
@with_module_nav('analytics', 'settings')
@htmx_view('analytics/pages/settings.html', 'analytics/partials/settings_content.html')
def settings_view(request):
    hub = _hub_id(request)
    settings = AnalyticsSettings.get_settings(hub)
    form = AnalyticsSettingsForm(instance=settings)

    # Saved reports
    saved_reports = SavedReport.objects.filter(
        hub_id=hub, is_deleted=False,
    ).order_by('-updated_at')

    return {
        'settings': settings,
        'form': form,
        'saved_reports': saved_reports,
    }


@require_http_methods(["POST"])
@login_required
@permission_required('analytics.manage_settings')
def settings_save(request):
    """Save analytics settings."""
    hub = _hub_id(request)

    try:
        settings = AnalyticsSettings.get_settings(hub)
        form = AnalyticsSettingsForm(request.POST, instance=settings)

        if form.is_valid():
            form.save()
            return JsonResponse({'success': True})
        else:
            return JsonResponse({
                'success': False,
                'errors': form.errors,
            }, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
