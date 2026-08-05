from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIRequestFactory
from .serializers import ItemSerializer
from .views import MenuEntryViewSet, aggregate_purchase_suggestions, build_menu_inventory_alerts
from .models import AuthAccount, Item, MenuEntry


class AuthEndpointTests(APITestCase):
    def test_register_and_login_work_with_backend(self):
        register_url = reverse('auth-register')
        response = self.client.post(register_url, {
            'name': 'Test User',
            'email': 'test@example.com',
            'password': 'secret123',
            'role': 'storekeeper',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['email'], 'test@example.com')
        self.assertEqual(AuthAccount.objects.count(), 1)

        login_url = reverse('auth-login')
        login_response = self.client.post(login_url, {
            'email': 'test@example.com',
            'password': 'secret123',
        }, format='json')

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.json()['email'], 'test@example.com')
        self.assertEqual(login_response.json()['role'], 'storekeeper')


class AdminEndpointsTests(APITestCase):
    def test_users_and_audit_logs_are_available(self):
        create_response = self.client.post(reverse('users-list'), {
            'name': 'Admin User',
            'email': 'admin@example.com',
            'password': 'secret123',
            'role': 'admin',
            'performed_by': 'System',
        }, format='json')

        self.assertEqual(create_response.status_code, 201)

        users_response = self.client.get(reverse('users-list'))
        self.assertEqual(users_response.status_code, 200)
        self.assertGreaterEqual(len(users_response.json()), 1)

        logs_response = self.client.get(reverse('audit-logs-list'))
        self.assertEqual(logs_response.status_code, 200)
        self.assertGreaterEqual(len(logs_response.json()), 1)


class ItemSerializerTests(SimpleTestCase):
    def test_negative_quantity_is_rejected(self):
        item = type(
            'ItemStub',
            (),
            {
                'id': 1,
                'name': 'Rice',
                'category': 'Staples',
                'quantity': 15,
                'unit': 'kg',
                'reorder_level': 10,
                'status': 'Healthy',
            },
        )()

        serializer = ItemSerializer(instance=item, data={'quantity': -5}, partial=True)

        self.assertFalse(serializer.is_valid())
        self.assertIn('You are trying to release that which is not available.', serializer.errors['quantity'])


class AlertGenerationTests(SimpleTestCase):
    def test_missing_or_low_inventory_items_are_reported_for_menus(self):
        inventory_items = [
            type('ItemStub', (), {'name': 'Rice', 'quantity': 3})(),
            type('ItemStub', (), {'name': 'Beans', 'quantity': 10})(),
        ]
        menu_entries = [
            type('MenuStub', (), {'day': 'Monday', 'cell': 'A', 'meal_type': 'Breakfast', 'menu_items': [{'item': 'Rice', 'quantity': '5'}, {'item': 'Oil', 'quantity': '2'}]})(),
        ]

        alerts = build_menu_inventory_alerts(menu_entries, inventory_items)

        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0]['item'], 'Rice')
        self.assertEqual(alerts[0]['required_quantity'], 5)
        self.assertEqual(alerts[0]['available_quantity'], 3)
        self.assertEqual(alerts[0]['shortage_quantity'], 2)
        self.assertFalse(alerts[0]['sufficient'])
        self.assertEqual(alerts[1]['item'], 'Oil')
        self.assertEqual(alerts[1]['available_quantity'], 0)
        self.assertEqual(alerts[1]['shortage_quantity'], 2)
        self.assertFalse(alerts[1]['sufficient'])

    def test_purchase_suggestions_are_aggregated_for_low_stock(self):
        inventory_items = [
            type('ItemStub', (), {'name': 'Rice', 'quantity': 3})(),
        ]
        menu_entries = [
            type('MenuStub', (), {'day': 'Tuesday', 'cell': 'B', 'meal_type': 'Lunch', 'menu_items': [{'item': 'Rice', 'quantity': '5'}]})(),
            type('MenuStub', (), {'day': 'Tuesday', 'cell': 'B', 'meal_type': 'Dinner', 'menu_items': [{'item': 'Rice', 'quantity': '4'}]})(),
        ]

        alerts = build_menu_inventory_alerts(menu_entries, inventory_items, day='Tuesday')
        self.assertEqual(len(alerts), 2)

        from .views import aggregate_purchase_suggestions
        purchase_suggestions = aggregate_purchase_suggestions(alerts)

        self.assertEqual(len(purchase_suggestions), 1)
        self.assertEqual(purchase_suggestions[0]['item'], 'Rice')
        self.assertEqual(purchase_suggestions[0]['required_quantity'], 9)
        self.assertEqual(purchase_suggestions[0]['available_quantity'], 3)
        self.assertEqual(purchase_suggestions[0]['shortage_quantity'], 6)

    def test_next_day_alerts_can_be_computed_from_current_day(self):
        inventory_items = [
            type('ItemStub', (), {'name': 'Rice', 'quantity': 2})(),
        ]
        menu_entries = [
            type('MenuStub', (), {'day': 'Wednesday', 'cell': 'C', 'meal_type': 'Breakfast', 'menu_items': [{'item': 'Rice', 'quantity': '4'}]})(),
        ]

        alerts = build_menu_inventory_alerts(menu_entries, inventory_items, day='Wednesday')
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['day'], 'Wednesday')
        self.assertEqual(alerts[0]['shortage_quantity'], 2)

    def test_next_day_purchase_alerts_endpoint_requires_current_day(self):
        factory = APIRequestFactory()
        request = factory.get('/menus/next-day-purchase-alerts')
        view = MenuEntryViewSet.as_view({'get': 'next_day_purchase_alerts'})
        response = view(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], 'current_day query parameter is required.')

    def test_next_day_purchase_alerts_endpoint_returns_suggestions(self):
        Item.objects.create(name='Rice', category='Staples', quantity=2, unit='kg', reorder_level=0)
        MenuEntry.objects.create(
            day='Wednesday',
            cell='C',
            cell_leader='Leader',
            meal_type='Breakfast',
            meal_name='Morning Meal',
            menu_items=[{'item': 'Rice', 'quantity': '4'}],
        )

        factory = APIRequestFactory()
        request = factory.get('/menus/next-day-purchase-alerts?current_day=Tuesday')
        view = MenuEntryViewSet.as_view({'get': 'next_day_purchase_alerts'})
        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['next_day'], 'Wednesday')
        self.assertEqual(len(response.data['purchase_suggestions']), 1)
        self.assertEqual(response.data['purchase_suggestions'][0]['item'], 'Rice')
        self.assertEqual(response.data['purchase_suggestions'][0]['shortage_quantity'], 2)
