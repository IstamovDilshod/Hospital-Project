from django.urls import reverse

from .models import Appointment, Notification


def _name(user):
    return user.get_full_name() or user.username


def _when(appt):
    return f"{appt.date:%d.%m.%Y} soat {appt.time:%H:%M}"


def notify(user, title, text="", kind=Notification.Kind.INFO, url="", key=""):
    """Bildirishnoma yaratadi. key berilsa, bir xil key ikki marta yaratilmaydi."""
    data = {"title": title, "text": text, "kind": kind, "url": url}
    if key:
        obj, created = Notification.objects.get_or_create(user=user, key=key, defaults=data)
        return obj if created else None
    return Notification.objects.create(user=user, **data)


def notify_booked(appt):
    doctor = appt.doctor
    notify(
        appt.patient, "Qabulga yozildingiz",
        f"{_name(doctor.user)} ({doctor.specialty}) · {_when(appt)}",
        Notification.Kind.BOOKED, reverse("my_appointments"),
    )
    notify(
        doctor.user, "Yangi qabul",
        f"{_name(appt.patient)} · {_when(appt)}",
        Notification.Kind.BOOKED, reverse("dpanel_appointment", args=[appt.pk]),
    )


def notify_confirmed(appt):
    notify(
        appt.patient, "Qabulingiz tasdiqlandi",
        f"{_name(appt.doctor.user)} · {_when(appt)}",
        Notification.Kind.CONFIRMED, reverse("my_appointments"),
    )


def notify_cancelled(appt, actor):
    """Qabul bekor qilinganda, bekor qilgan odamdan boshqa tomonlarga xabar beradi."""
    doctor = appt.doctor
    if actor.pk != appt.patient_id:
        notify(
            appt.patient, "Qabulingiz bekor qilindi",
            f"{_name(doctor.user)} · {_when(appt)}",
            Notification.Kind.CANCELLED, reverse("my_appointments"),
        )
    if actor.pk != doctor.user_id:
        notify(
            doctor.user, "Qabul bekor qilindi",
            f"{_name(appt.patient)} · {_when(appt)}",
            Notification.Kind.CANCELLED, reverse("dpanel_appointments"),
        )


def notify_status_change(appt, old_status, actor):
    S = Appointment.Status
    if appt.status == S.CANCELLED and old_status != S.CANCELLED:
        notify_cancelled(appt, actor)
    elif appt.status == S.CONFIRMED and old_status == S.PENDING:
        notify_confirmed(appt)