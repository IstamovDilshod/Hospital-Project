from django.db import models
from datetime import datetime, timedelta

from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Hospital(models.Model):
    name = models.CharField("Nomi", max_length=200)
    address = models.CharField("Manzil", max_length=300)
    phone = models.CharField("Telefon", max_length=20, blank=True)
    description = models.TextField("Tavsif", blank=True)
    logo = models.ImageField(upload_to="hospitals/", blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Kasalxona"
        verbose_name_plural = "Kasalxonalar"

    def __str__(self):
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        PATIENT = "patient", "Bemor"
        DOCTOR = "doctor", "Shifokor"
        HOSPITAL_ADMIN = "hospital_admin", "Kasalxona admini"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PATIENT)
    phone = models.CharField("Telefon", max_length=20, unique=True, null=True, blank=True)
    birth_date = models.DateField("Tug'ilgan sana", null=True, blank=True)
    # faqat hospital_admin uchun: qaysi kasalxonani boshqaradi
    hospital = models.ForeignKey(
        Hospital, on_delete=models.SET_NULL, null=True, blank=True, related_name="staff"
    )
    must_change_password = models.BooleanField("Parolni almashtirishi shart", default=False)

    @property
    def is_patient(self):
        return self.role == self.Role.PATIENT

    @property
    def is_doctor(self):
        return self.role == self.Role.DOCTOR

    @property
    def is_hospital_admin(self):
        return self.role == self.Role.HOSPITAL_ADMIN

    def __str__(self):
        return self.get_full_name() or self.username


class Department(models.Model):
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name="departments")
    name = models.CharField("Bo'lim nomi", max_length=150)

    class Meta:
        verbose_name = "Bo'lim"
        verbose_name_plural = "Bo'limlar"

    def __str__(self):
        return f"{self.name} ({self.hospital})"


class Specialty(models.Model):
    name = models.CharField("Mutaxassislik", max_length=100, unique=True)

    class Meta:
        verbose_name = "Mutaxassislik"
        verbose_name_plural = "Mutaxassisliklar"

    def __str__(self):
        return self.name


class Doctor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="doctor_profile")
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name="doctors")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    specialty = models.ForeignKey(Specialty, on_delete=models.PROTECT, related_name="doctors")
    experience_years = models.PositiveSmallIntegerField("Tajriba (yil)", default=0)
    price = models.PositiveIntegerField("Qabul narxi (so'm)", default=0)
    bio = models.TextField("Haqida", blank=True)
    photo = models.ImageField(upload_to="doctors/", blank=True, null=True)
    slot_minutes = models.PositiveSmallIntegerField("Bir qabul davomiyligi (daqiqa)", default=20)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Shifokor"
        verbose_name_plural = "Shifokorlar"

    def __str__(self):
        return f"{self.user} - {self.specialty}"

    def get_available_slots(self, date, lead_minutes=0):
        """Berilgan sana uchun bo'sh vaqtlar ro'yxatini qaytaradi."""
        now = timezone.localtime()

        if date < now.date():
            return []
        if self.time_offs.filter(start_date__lte=date, end_date__gte=date).exists():
            return []

        booked = set(
            self.appointments.filter(date=date)
            .exclude(status=Appointment.Status.CANCELLED)
            .values_list("time", flat=True)
        )

        step = timedelta(minutes=self.slot_minutes)
        slots = []
        for sch in self.schedules.filter(weekday=date.weekday()).order_by("start_time"):
            current = datetime.combine(date, sch.start_time)
            end = datetime.combine(date, sch.end_time)
            while current + step <= end:
                t = current.time()
                is_past = timezone.make_aware(current) <= now + timedelta(minutes=lead_minutes)
                if t not in booked and not is_past:
                    slots.append(t)
                current += step
        return slots

    @property
    def average_rating(self):
        return self.appointments.filter(review__isnull=False).aggregate(
            avg=models.Avg("review__rating")
        )["avg"]


class WorkSchedule(models.Model):
    """Shifokorning haftalik ish jadvali. Tanaffus uchun bir kunga ikkita oraliq qo'shiladi."""

    class Weekday(models.IntegerChoices):
        MON = 0, "Dushanba"
        TUE = 1, "Seshanba"
        WED = 2, "Chorshanba"
        THU = 3, "Payshanba"
        FRI = 4, "Juma"
        SAT = 5, "Shanba"
        SUN = 6, "Yakshanba"

    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="schedules")
    weekday = models.IntegerField("Hafta kuni", choices=Weekday.choices)
    start_time = models.TimeField("Boshlanish")
    end_time = models.TimeField("Tugash")

    class Meta:
        verbose_name = "Ish jadvali"
        verbose_name_plural = "Ish jadvallari"
        ordering = ["weekday", "start_time"]

    def __str__(self):
        return f"{self.doctor} - {self.get_weekday_display()} {self.start_time:%H:%M}-{self.end_time:%H:%M}"


class TimeOff(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="time_offs")
    start_date = models.DateField("Boshlanish sanasi")
    end_date = models.DateField("Tugash sanasi")
    reason = models.CharField("Sabab", max_length=200, blank=True)

    class Meta:
        verbose_name = "Dam olish"
        verbose_name_plural = "Dam olish kunlari"

    def __str__(self):
        return f"{self.doctor}: {self.start_date} - {self.end_date}"


class Appointment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        CONFIRMED = "confirmed", "Tasdiqlangan"
        COMPLETED = "completed", "Yakunlangan"
        CANCELLED = "cancelled", "Bekor qilingan"
        NO_SHOW = "no_show", "Kelmadi"

    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="appointments")
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="appointments")
    date = models.DateField("Sana")
    time = models.TimeField("Vaqt")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMED)
    complaint = models.TextField("Shikoyat / izoh", blank=True)
    doctor_note = models.TextField("Shifokor izohi", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Qabul"
        verbose_name_plural = "Qabullar"
        ordering = ["-date", "-time"]
        constraints = [
            # Bir shifokorga bir vaqtga faqat bitta faol qabul (bekor qilinganlar hisobga olinmaydi)
            models.UniqueConstraint(
                fields=["doctor", "date", "time"],
                condition=~Q(status="cancelled"),
                name="unique_active_slot",
            )
        ]

    def __str__(self):
        return f"{self.patient} -> {self.doctor} ({self.date} {self.time:%H:%M})"


class Review(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name="review")
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField("Sharh", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Sharh"
        verbose_name_plural = "Sharhlar"

    def __str__(self):
        return f"{self.appointment} - {self.rating}"


class Notification(models.Model):
    class Kind(models.TextChoices):
        BOOKED = "booked", "Yangi qabul"
        CONFIRMED = "confirmed", "Tasdiqlandi"
        CANCELLED = "cancelled", "Bekor qilindi"
        REMINDER = "reminder", "Eslatma"
        INFO = "info", "Xabar"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.INFO)
    title = models.CharField(max_length=120)
    text = models.CharField(max_length=255, blank=True)
    url = models.CharField(max_length=200, blank=True)
    # takroriy yuborilishni oldini olish uchun (masalan, "remind24:15")
    key = models.CharField(max_length=60, blank=True, default="")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Bildirishnoma"
        verbose_name_plural = "Bildirishnomalar"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "key"],
                condition=~Q(key=""),
                name="unique_notification_key",
            )
        ]

    def __str__(self):
        return f"{self.user}: {self.title}"
