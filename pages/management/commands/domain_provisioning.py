from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from pages.models import Domain


class Command(BaseCommand):
    help = "Coordinate the host-side custom-domain HTTPS provisioner."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["list", "start", "success", "fail"])
        parser.add_argument("hostname", nargs="?")
        parser.add_argument("--error", default="")

    def handle(self, *args, **options):
        action = options["action"]
        if action == "list":
            now = timezone.now()
            due = Domain.objects.filter(
                Q(status=Domain.STATUS_PROVISIONING)
                | Q(status=Domain.STATUS_FAILED, next_provision_at__lte=now)
            ).filter(Q(next_provision_at__isnull=True) | Q(next_provision_at__lte=now))
            for hostname in due.order_by("created_at").values_list("hostname", flat=True):
                self.stdout.write(hostname)
            return

        hostname = (options.get("hostname") or "").lower().rstrip(".")
        if not hostname:
            raise CommandError("hostname is required")
        try:
            domain = Domain.objects.get(hostname=hostname)
        except Domain.DoesNotExist as exc:
            raise CommandError(f"Unknown domain: {hostname}") from exc

        if action == "start":
            if domain.status == Domain.STATUS_VERIFIED:
                self.stdout.write("already active")
                return
            domain.status = Domain.STATUS_PROVISIONING
            domain.provisioning_attempts += 1
            domain.provisioning_error = ""
            domain.next_provision_at = None
            domain.save(update_fields=[
                "status", "provisioning_attempts", "provisioning_error", "next_provision_at",
            ])
            self.stdout.write(f"attempt {domain.provisioning_attempts}")
            return

        if action == "success":
            domain.status = Domain.STATUS_VERIFIED
            domain.provisioning_error = ""
            domain.next_provision_at = None
            domain.provisioned_at = timezone.now()
            domain.save(update_fields=[
                "status", "provisioning_error", "next_provision_at", "provisioned_at",
            ])
            self.stdout.write("active")
            return

        error = (options.get("error") or "Provisioning failed")[-4000:]
        delay_minutes = min(5 * (2 ** max(domain.provisioning_attempts - 1, 0)), 360)
        domain.status = Domain.STATUS_FAILED
        domain.provisioning_error = error
        domain.next_provision_at = timezone.now() + timedelta(minutes=delay_minutes)
        domain.save(update_fields=["status", "provisioning_error", "next_provision_at"])
        self.stdout.write(f"retry in {delay_minutes} minutes")
