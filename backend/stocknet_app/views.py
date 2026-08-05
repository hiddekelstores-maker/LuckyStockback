from collections import defaultdict
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import Item, Purchase, ProcurementRequest, Delivery, Invoice, Payment, GoodsReceipt, Tender, Bid, MenuEntry, ReleaseEntry, AuthAccount, AuditLog
from .serializers import ItemSerializer, PurchaseSerializer, ProcurementRequestSerializer, DeliverySerializer, InvoiceSerializer, PaymentSerializer, GoodsReceiptSerializer, TenderSerializer, BidSerializer, MenuEntrySerializer, ReleaseEntrySerializer, AuthAccountSerializer, AuditLogSerializer


@method_decorator(csrf_exempt, name='dispatch')
class AuthViewSet(viewsets.ViewSet):
    def create(self, request, *args, **kwargs):
        email = (request.data.get('email') or '').strip().lower()
        password = request.data.get('password') or ''
        name = (request.data.get('name') or '').strip()
        role = (request.data.get('role') or 'storekeeper').strip()

        if not email or not password or not name:
            return Response({'detail': 'Name, email, and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        if AuthAccount.objects.filter(email__iexact=email).exists():
            return Response({'detail': 'Account already exists.'}, status=status.HTTP_409_CONFLICT)

        account = AuthAccount.objects.create(name=name, email=email, password=password, role=role)
        return Response({'id': account.id, 'name': account.name, 'email': account.email, 'role': account.role}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='login')
    def login(self, request, *args, **kwargs):
        email = (request.data.get('email') or '').strip().lower()
        password = request.data.get('password') or ''

        if not email or not password:
            return Response({'detail': 'Email and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        account = AuthAccount.objects.filter(email__iexact=email, password=password).first()
        if not account:
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        return Response({'id': account.id, 'name': account.name, 'email': account.email, 'role': account.role})


NEXT_DAY_MAPPING = {
    'monday': 'Tuesday',
    'tuesday': 'Wednesday',
    'wednesday': 'Thursday',
    'thursday': 'Friday',
    'friday': 'Saturday',
    'saturday': 'Sunday',
    'sunday': 'Monday',
}


def normalize_day(day):
    return day.strip().lower() if isinstance(day, str) else None


def parse_int_quantity(value):
    if value is None or value == '':
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def build_menu_inventory_alerts(menu_entries, inventory_items, day=None):
    inventory_lookup = {item.name.strip().lower(): item for item in inventory_items}
    alerts = []
    day_filter = normalize_day(day)

    for entry in menu_entries:
        if day_filter and normalize_day(entry.day) != day_filter:
            continue

        for menu_item in entry.menu_items or []:
            item_name = (menu_item.get('item') or '').strip()
            required_quantity = parse_int_quantity(menu_item.get('quantity'))
            if not item_name:
                continue

            available = inventory_lookup.get(item_name.lower())
            available_quantity = available.quantity if available else 0
            alerts.append({
                'item': item_name,
                'required_quantity': required_quantity,
                'available_quantity': available_quantity,
                'shortage_quantity': max(0, required_quantity - available_quantity),
                'sufficient': available_quantity >= required_quantity,
                'day': entry.day,
                'meal_type': entry.meal_type,
                'cell': entry.cell,
            })

    return alerts


def aggregate_purchase_suggestions(alerts):
    grouped = defaultdict(lambda: {
        'required_quantity': 0,
        'available_quantity': 0,
        'shortage_quantity': 0,
        'details': [],
    })

    for alert in alerts:
        item_name = alert['item']
        grouped[item_name]['required_quantity'] += alert['required_quantity']
        grouped[item_name]['available_quantity'] = alert['available_quantity']
        grouped[item_name]['shortage_quantity'] = max(0, grouped[item_name]['required_quantity'] - grouped[item_name]['available_quantity'])
        grouped[item_name]['details'].append({
            'day': alert['day'],
            'meal_type': alert['meal_type'],
            'cell': alert['cell'],
            'required_quantity': alert['required_quantity'],
            'available_quantity': alert['available_quantity'],
            'shortage_quantity': alert['shortage_quantity'],
        })

    return [
        {
            'item': item_name,
            'required_quantity': data['required_quantity'],
            'available_quantity': data['available_quantity'],
            'shortage_quantity': data['shortage_quantity'],
            'details': data['details'],
        }
        for item_name, data in grouped.items()
        if data['shortage_quantity'] > 0
    ]


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all().order_by('-id')
    serializer_class = ItemSerializer

    def create(self, request, *args, **kwargs):
        existing = Item.objects.filter(name__iexact=request.data.get('name', '').strip(), category__iexact=request.data.get('category', '').strip()).first()
        if existing:
            payload = request.data.copy()
            payload['quantity'] = existing.quantity + int(payload.get('quantity', 0) or 0)
            payload['status'] = 'Low' if payload['quantity'] <= existing.reorder_level else 'Healthy'
            serializer = self.get_serializer(existing, data=payload, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            AuditLog.objects.create(
                actor=request.data.get('performed_by') or 'System',
                action='updated_inventory',
                details=f"Updated inventory item {existing.name} with quantity {payload['quantity']}",
            )
            return Response(serializer.data, status=status.HTTP_200_OK)

        response = super().create(request, *args, **kwargs)
        item_name = request.data.get('name', '').strip()
        AuditLog.objects.create(
            actor=request.data.get('performed_by') or 'System',
            action='created_inventory',
            details=f"Created inventory item {item_name}",
        )
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        instance = self.get_object()
        AuditLog.objects.create(
            actor=request.data.get('performed_by') or 'System',
            action='updated_inventory',
            details=f"Updated inventory item {instance.name}",
        )
        return response


class PurchaseViewSet(viewsets.ModelViewSet):
    queryset = Purchase.objects.all().order_by('-id')
    serializer_class = PurchaseSerializer


class ProcurementRequestViewSet(viewsets.ModelViewSet):
    queryset = ProcurementRequest.objects.all().order_by('-id')
    serializer_class = ProcurementRequestSerializer


class DeliveryViewSet(viewsets.ModelViewSet):
    queryset = Delivery.objects.all().order_by('-id')
    serializer_class = DeliverySerializer


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all().order_by('-id')
    serializer_class = InvoiceSerializer


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all().order_by('-id')
    serializer_class = PaymentSerializer


class TenderViewSet(viewsets.ModelViewSet):
    queryset = Tender.objects.all().order_by('-id')
    serializer_class = TenderSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request is not None and self.request.query_params.get('published') == 'true':
            queryset = queryset.filter(published=True)
        return queryset


class BidViewSet(viewsets.ModelViewSet):
    queryset = Bid.objects.all().order_by('-id')
    serializer_class = BidSerializer


class GoodsReceiptViewSet(viewsets.ModelViewSet):
    queryset = GoodsReceipt.objects.all().order_by('-id')
    serializer_class = GoodsReceiptSerializer


class MenuEntryViewSet(viewsets.ModelViewSet):
    queryset = MenuEntry.objects.all().order_by('-id')
    serializer_class = MenuEntrySerializer

    @action(detail=False, methods=['get'])
    def alerts(self, request, *args, **kwargs):
        inventory_items = Item.objects.all()
        menu_entries = self.get_queryset()

        # Accept either a direct day or a current_day that is used to plan for the next day.
        day = request.query_params.get('day')
        current_day = request.query_params.get('current_day')
        if not day and current_day:
            normalized_current = normalize_day(current_day)
            day = NEXT_DAY_MAPPING.get(normalized_current)

        alerts = build_menu_inventory_alerts(menu_entries, inventory_items, day=day)
        purchase_suggestions = aggregate_purchase_suggestions(alerts)

        return Response({
            'day': day,
            'current_day': current_day,
            'alerts': alerts,
            'purchase_suggestions': purchase_suggestions,
        })

    @action(detail=False, methods=['get'], url_path='next-day-purchase-alerts')
    def next_day_purchase_alerts(self, request, *args, **kwargs):
        current_day = request.query_params.get('current_day')
        if not current_day:
            return Response({'detail': 'current_day query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        next_day = NEXT_DAY_MAPPING.get(normalize_day(current_day))
        if not next_day:
            return Response({'detail': 'current_day must be a valid weekday.'}, status=status.HTTP_400_BAD_REQUEST)

        inventory_items = Item.objects.all()
        menu_entries = self.get_queryset()
        alerts = build_menu_inventory_alerts(menu_entries, inventory_items, day=next_day)
        purchase_suggestions = aggregate_purchase_suggestions(alerts)

        return Response({
            'current_day': current_day,
            'next_day': next_day,
            'purchase_suggestions': purchase_suggestions,
        })


class ReleaseEntryViewSet(viewsets.ModelViewSet):
    queryset = ReleaseEntry.objects.all().order_by('-id')
    serializer_class = ReleaseEntrySerializer

    @action(detail=False, methods=['get'])
    def logs(self, request, *args, **kwargs):
        release_entries = self.get_queryset()
        item_entries = Item.objects.all().order_by('-id')

        log_entries = []
        for entry in release_entries:
            log_entries.append({
                'type': 'release',
                'description': f"{entry.person_given} received {entry.quantity} {entry.unit} of {entry.item}",
                'performed_by': entry.person_given,
                'target': entry.item,
                'timestamp': entry.id,
                'day': entry.day,
                'meal_type': entry.meal_type,
            })

        for item in item_entries:
            log_entries.append({
                'type': 'creation',
                'description': f"{item.name} was created or updated in inventory",
                'performed_by': 'System',
                'target': item.name,
                'timestamp': item.id,
                'category': item.category,
                'quantity': item.quantity,
            })

        log_entries.sort(key=lambda item: item['timestamp'], reverse=True)
        return Response(log_entries)


class UserManagementViewSet(viewsets.ModelViewSet):
    queryset = AuthAccount.objects.all().order_by('-id')
    serializer_class = AuthAccountSerializer

    def create(self, request, *args, **kwargs):
        payload = request.data.copy()
        payload['password'] = payload.get('password', '')
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        AuditLog.objects.create(actor=request.data.get('performed_by') or 'Admin', action='created_user', details=f"Created user {instance.email}")
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        instance = self.get_object()
        AuditLog.objects.create(actor=request.data.get('performed_by') or 'Admin', action='updated_user', details=f"Updated user {instance.email}")
        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        response = super().destroy(request, *args, **kwargs)
        AuditLog.objects.create(actor=request.data.get('performed_by') or 'Admin', action='deleted_user', details=f"Deleted user {instance.email}")
        return response


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all().order_by('-created_at')
    serializer_class = AuditLogSerializer
