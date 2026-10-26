from datetime import datetime, timedelta

from django.utils import timezone

from .models import Appointment

LEAD_MINUTES = 60           # qabulga shuncha vaqt qolganda yozilish yopiladi
CANCEL_LOCK_MINUTES = 60    # qabulga shuncha vaqt qolganda bekor qilib bo'lmaydi
MAX_DAYS_AHEAD = 60
MAX_PER_DAY = 2
MAX_UPCOMING = 5
MAX_CREATED_24H = 6
MAX_NO_SHOWS = 3
NO_SHOW_DAYS = 90

S = Appointment.Status
ACTIVE = (S.PENDING, S.CONFIRMED)


def start_of(day, slot):
    return timezone.make_aware(datetime.combine(day, slot))


def max_date():
    return timezone.localdate() + timedelta(days=MAX_DAYS_AHEAD)


def check_patient_limits(patient, doctor, day, slot):
    """Onlayn yozilishdan oldin tekshiradi. Xato matnini yoki None qaytaradi."""
    now = timezone.now()
    today = timezone.localdate()

    if day > max_date():
        return f"Faqat {MAX_DAYS_AHEAD} kun oldindan yozilish mumkin."
    if start_of(day, slot) - now < timedelta(minutes=LEAD_MINUTES):
        return f"Qabulga {LEAD_MINUTES} daqiqadan kam qolgan. Iltimos, registraturaga qo'ng'iroq qiling."

    mine = Appointment.objects.filter(patient=patient)

    no_shows = mine.filter(
        status=S.NO_SHOW, date__gte=today - timedelta(days=NO_SHOW_DAYS)
    ).count()
    if no_shows >= MAX_NO_SHOWS:
        return (
            f"Oxirgi {NO_SHOW_DAYS} kunda {no_shows} marta qabulga kelmagansiz, "
            "shuning uchun onlayn yozilish vaqtincha yopilgan. Registratura orqali yoziling."
        )

    if mine.filter(created_at__gte=now - timedelta(hours=24)).count() >= MAX_CREATED_24H:
        return "Juda ko'p urinish bo'ldi. Iltimos, keyinroq qayta urinib ko'ring."

    active = mine.filter(status__in=ACTIVE)
    if active.filter(date__gte=today).count() >= MAX_UPCOMING:
        return f"Bir vaqtda {MAX_UPCOMING} tadan ortiq faol qabulingiz bo'lishi mumkin emas."
    if active.filter(date=day).count() >= MAX_PER_DAY:
        return f"Bir kunga {MAX_PER_DAY} tadan ortiq qabulga yozilib bo'lmaydi."
    if active.filter(date=day, doctor=doctor).exists():
        return "Bu shifokorga shu kunga allaqachon yozilgansiz."
    if active.filter(date=day, time=slot).exists():
        return "Shu vaqtda sizda boshqa qabul bor."
    return None


def can_cancel(appt):
    """(mumkinmi, izoh) qaytaradi."""
    if appt.status not in ACTIVE:
        return False, ""
    left = start_of(appt.date, appt.time) - timezone.now()
    if left <= timedelta(0):
        return False, ""
    if left < timedelta(minutes=CANCEL_LOCK_MINUTES):
        return False, "Qabulga 1 soatdan kam qolgan. Bekor qilish uchun registraturaga qo'ng'iroq qiling."
    return True, ""