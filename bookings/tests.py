from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from django.contrib.auth import get_user_model
from django.test import TestCase
from commerce.models import Customer
from .models import BookingType, CalendarConnection, Host, WorkingHours
from .services import create_booking, host_is_free

class BookingTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user("calendar@example.com")
        self.hosts = []
        for index in range(2):
            connection = CalendarConnection.objects.create(user=user, email=f"host{index}@example.com")
            host = Host.objects.create(name=f"Host {index}", calendar=connection)
            self.hosts.append(host)
        self.kind = BookingType.objects.create(name_en="Consultation", slug="consultation", duration_minutes=60, minimum_notice_hours=0)
        self.kind.hosts.set(self.hosts)
        self.customer = Customer.objects.create(email="customer@example.com")

    def test_round_robin_uses_next_available_host(self):
        start = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")) + timedelta(days=2)
        start = start.replace(hour=10, minute=0, second=0, microsecond=0)
        first = create_booking(self.kind, self.customer, start)
        second = create_booking(self.kind, self.customer, start)
        self.assertNotEqual(first.host_id, second.host_id)
        self.assertFalse(host_is_free(first.host, start, start + timedelta(hours=1)))

