from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from clin_app.models import Appointment, Notification
from clin_app.notifications import notify


class Command(BaseCommand):
    help = "Qabuldan 24 soat va 2 soat oldin bemorlarga eslatma yuboradi."

    def add_arguments(self, parser):
        parser.add_argument(
            "--test", action="store_true",
            help="Qabul qachon yaratilganini tekshirmasdan eslatma yuboradi (sinash uchun)",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        today = timezone.localdate()
        appointments = Appointment.objects.filter(
            status__in=[Appointment.Status.PENDING, Appointment.Status.CONFIRMED],
            date__range=(today, today + timedelta(days=1)),
        ).select_related("patient", "doctor__user", "doctor__specialty")

        sent = 0
        for appt in appointments:
            start = timezone.make_aware(datetime.combine(appt.date, appt.time))
            left = start - now
            if left <= timedelta(0):
                continue

            if left <= timedelta(hours=2):
                stage, hours, title = "remind2", 2, "Qabulgacha 2 soat qoldi"
            elif left <= timedelta(hours=24):
                stage, hours, title = "remind24", 24, "Qabul eslatmasi"
            else:
                continue

            # Qabul eslatma vaqtidan keyin yozilgan bo'lsa, eslatma keraksiz
            if not options["test"] and appt.created_at > start - timedelta(hours=hours):
                continue

            doctor = appt.doctor
            result = notify(
                appt.patient, title,
                f"{doctor.user.get_full_name() or doctor.user.username} ({doctor.specialty}) · "
                f"{appt.date:%d.%m.%Y} soat {appt.time:%H:%M}",
                Notification.Kind.REMINDER, reverse("my_appointments"),
                key=f"{stage}:{appt.pk}",
            )
            if result:
                sent += 1

        self.stdout.write(self.style.SUCCESS(f"Yuborilgan eslatmalar: {sent}"))