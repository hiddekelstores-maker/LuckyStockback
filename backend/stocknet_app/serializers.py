from rest_framework import serializers
from .models import Item, Purchase, ProcurementRequest, Delivery, Invoice, Payment, GoodsReceipt, Tender, Bid, MenuEntry, ReleaseEntry, AuthAccount, AuditLog


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = '__all__'

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError('You are trying to release that which is not available.')
        return value


class PurchaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Purchase
        fields = '__all__'


class ProcurementRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcurementRequest
        fields = '__all__'


class DeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = Delivery
        fields = '__all__'


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = '__all__'


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'


class GoodsReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoodsReceipt
        fields = '__all__'


class TenderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tender
        fields = '__all__'


class BidSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bid
        fields = '__all__'


class MenuEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuEntry
        fields = '__all__'

    def validate_menu_items(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('menu_items must be a list of item dictionaries.')

        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError('Each menu item must be an object with item and quantity.')
            item_name = item.get('item')
            quantity = item.get('quantity')
            if not item_name or not str(item_name).strip():
                raise serializers.ValidationError('Menu item name is required.')
            try:
                quantity_int = int(quantity)
            except (TypeError, ValueError):
                raise serializers.ValidationError('Menu item quantity must be a whole number.')
            if quantity_int < 0:
                raise serializers.ValidationError('Menu item quantity cannot be negative.')
        return value


class ReleaseEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = ReleaseEntry
        fields = '__all__'


class AuthAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthAccount
        fields = ['id', 'name', 'email', 'role', 'password']
        extra_kwargs = {'password': {'write_only': True}}


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = '__all__'
