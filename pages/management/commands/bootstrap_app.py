from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand
from django.db import transaction
from automations.models import EmailTemplate, ReminderStep
from users.models import ApprovedEmail

class Command(BaseCommand):
    help = "Create the owner and default follow-up templates."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--password", default=None)

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["email"].lower()
        Site.objects.update_or_create(pk=1, defaults={"domain": "manager.cosmic135.com", "name": "Cosmic Launch"})
        ApprovedEmail.objects.update_or_create(email=email, defaults={"role": "owner", "active": True})
        user, created = get_user_model().objects.get_or_create(username=email, defaults={"email": email, "is_staff": True, "is_superuser": True})
        if options["password"]:
            user.set_password(options["password"])
            user.save()
        template, _ = EmailTemplate.objects.update_or_create(kind="action_request", name="Complete your next step", defaults={
            "subject_en": "Your next step with Cosmic135",
            "subject_zh": "您在 Cosmic135 的下一步",
            "body_en": "Hello {{ customer.name|default:customer.email }},\n\nYour payment is confirmed. Complete your next step here:\n{{ action_url }}\n\nReply to this email if you need help.",
            "body_zh": "您好，\n\n您的付款已确认。请在此完成下一步：\n{{ action_url }}\n\n如需帮助，请回复此邮件。",
            "active": True,
        })
        reminder, _ = EmailTemplate.objects.update_or_create(kind="reminder", name="Action reminder", defaults={
            "subject_en": "Reminder: please complete your next step",
            "subject_zh": "提醒：请完成您的下一步",
            "body_en": "Hello,\n\nYour next step is still waiting. Continue here:\n{{ action_url }}",
            "body_zh": "您好，\n\n您的下一步尚未完成。请点击：\n{{ action_url }}",
            "active": True,
        })
        for hours in (24, 72, 168):
            ReminderStep.objects.update_or_create(name=f"Reminder after {hours} hours", defaults={"delay_hours": hours, "template": reminder, "active": True})
        defaults = [
            ("payment_confirmation", "Payment confirmed", "Payment confirmed — Cosmic135", "付款已确认 — Cosmic135", "Thank you. Your payment has been confirmed.", "谢谢。您的付款已确认。"),
            ("booking_confirmation", "Booking confirmed", "Your booking is confirmed", "您的预约已确认", "Your appointment is confirmed for {{ booking.starts_at }}. Manage it here:\n{{ action_url }}", "您的预约时间为 {{ booking.starts_at }}。管理预约：\n{{ action_url }}"),
            ("booking_cancelled", "Booking cancelled", "Your booking was cancelled", "您的预约已取消", "Your appointment has been cancelled. Reply if you need help.", "您的预约已取消。如需帮助，请回复此邮件。"),
            ("booking_rescheduled", "Booking rescheduled", "Your booking was rescheduled", "您的预约已改期", "Your new appointment time is {{ booking.starts_at }}. Manage it here:\n{{ action_url }}", "您的新预约时间为 {{ booking.starts_at }}。管理预约：\n{{ action_url }}"),
        ]
        for kind, name, subject_en, subject_zh, body_en, body_zh in defaults:
            EmailTemplate.objects.update_or_create(kind=kind, name=name, defaults={
                "subject_en": subject_en, "subject_zh": subject_zh,
                "body_en": body_en, "body_zh": body_zh, "active": True,
            })
        self.stdout.write(self.style.SUCCESS(f"Cosmic Launch initialized for {email}"))

