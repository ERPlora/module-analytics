import csv
from datetime import timedelta
from decimal import Decimal

from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import login_required
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
