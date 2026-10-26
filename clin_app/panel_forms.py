from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
import re

from django.db.models import F, Value
from django.db.models.functions import Replace

from .models import Department, Doctor, Specialty, User, WorkSchedule


class DoctorForm(forms.ModelForm):
    first_name = forms.CharField(label="Ism", max_length=150)
    last_name = forms.CharField(label="Familiya", max_length=150)
    phone = forms.CharField(label="Telefon", max_length=20, required=False)
    username = forms.CharField(label="Login", max_length=150)
    password = forms.CharField(label="Parol", min_length=6, widget=forms.PasswordInput(render_value=False))

    field_order = [
        "first_name", "last_name", "phone", "username", "password",
        "specialty", "department", "experience_years", "price", "slot_minutes",
        "bio", "photo", "is_active",
    ]

    class Meta:
        model = Doctor
        fields = (
            "specialty", "department", "experience_years", "price",
            "slot_minutes", "bio", "photo", "is_active",
        )
        widgets = {"bio": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, hospital=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.hospital = hospital
        self.fields["department"].queryset = Department.objects.filter(hospital=hospital)
        self.fields["department"].required = False

        if self.instance.pk:
            user = self.instance.user
            self.fields["first_name"].initial = user.first_name
            self.fields["last_name"].initial = user.last_name
            self.fields["phone"].initial = user.phone
            self.fields["username"].initial = user.username
            self.fields["password"].required = False
            self.fields["password"].help_text = "Bo'sh qoldirsangiz, parol o'zgarmaydi."

    def clean_username(self):
        username = self.cleaned_data["username"]
        qs = User.objects.filter(username=username)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise ValidationError("Bu login band.")
        return username

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()
        if not phone:
            return None
        qs = User.objects.filter(phone=phone)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise ValidationError("Bu telefon raqami band.")
        return phone

    def save(self, commit=True):
        data = self.cleaned_data
        doctor = super().save(commit=False)

        user = self.instance.user if self.instance.pk else User(role=User.Role.DOCTOR)
        user.username = data["username"]
        user.first_name = data["first_name"]
        user.last_name = data["last_name"]
        user.phone = data["phone"]
        if data.get("password"):
            user.set_password(data["password"])
        user.save()

        doctor.user = user
        doctor.hospital = self.hospital
        doctor.save()
        return doctor


class WorkScheduleForm(forms.ModelForm):
    class Meta:
        model = WorkSchedule
        fields = ("weekday", "start_time", "end_time")
        widgets = {
            "start_time": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
            "end_time": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
        }

    def clean(self):
        data = super().clean()
        start, end = data.get("start_time"), data.get("end_time")
        if start and end and end <= start:
            raise ValidationError("Tugash vaqti boshlanishdan keyin bo'lishi kerak.")
        return data


ScheduleFormSet = inlineformset_factory(
    Doctor, WorkSchedule, form=WorkScheduleForm, extra=3, can_delete=True
)


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ("name",)
        widgets = {"name": forms.TextInput(attrs={"placeholder": "Masalan: Kardiologiya bo'limi"})}


class SpecialtyForm(forms.ModelForm):
    class Meta:
        model = Specialty
        fields = ("name",)
        widgets = {"name": forms.TextInput(attrs={"placeholder": "Masalan: Kardiolog"})}


def normalize_phone(raw):
    """Telefondan oxirgi 9 ta raqamni oladi (+998 90 123 45 67 -> 901234567)."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("998"):
        digits = digits[3:]
    if len(digits) != 9:
        raise ValidationError("Telefon raqami noto'g'ri. Masalan: 90 123 45 67")
    return digits


def find_user_by_phone(last9):
    """Telefon qanday yozilgan bo'lsa ham (probel, +, -) topadi."""
    expr = F("phone")
    for ch in (" ", "+", "-", "(", ")"):
        expr = Replace(expr, Value(ch), Value(""))
    return (
        User.objects.exclude(phone__isnull=True)
        .annotate(digits=expr)
        .filter(digits__endswith=last9)
        .first()
    )


class ManualBookingForm(forms.Form):
    doctor = forms.ModelChoiceField(queryset=Doctor.objects.none(), label="Shifokor")
    date = forms.DateField(label="Sana", widget=forms.DateInput(attrs={"type": "date"}))
    time = forms.TimeField(
        label="Vaqt", input_formats=["%H:%M"],
        error_messages={"required": "Vaqtni tanlang."},
    )
    phone = forms.CharField(
        label="Bemor telefoni", max_length=20,
        widget=forms.TextInput(attrs={"placeholder": "90 123 45 67"}),
    )
    first_name = forms.CharField(label="Ism", max_length=150, required=False)
    last_name = forms.CharField(label="Familiya", max_length=150, required=False)
    complaint = forms.CharField(
        label="Shikoyat (ixtiyoriy)", required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, hospital=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["doctor"].queryset = Doctor.objects.filter(
            hospital=hospital, is_active=True
        ).select_related("user", "specialty")
        self.fields["doctor"].label_from_instance = (
            lambda d: f"{d.user.get_full_name() or d.user.username} · {d.specialty}"
        )
        self.patient = None   # topilgan mavjud bemor
        self.last9 = None     # telefonning oxirgi 9 raqami

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        self.last9 = normalize_phone(phone)
        return phone

    def clean(self):
        data = super().clean()

        if self.last9:
            user = find_user_by_phone(self.last9)
            if user and user.role != User.Role.PATIENT:
                self.add_error("phone", "Bu raqam xodimga tegishli. Bemorning raqamini kiriting.")
            elif user:
                self.patient = user
            else:
                for field in ("first_name", "last_name"):
                    if not data.get(field):
                        self.add_error(field, "Yangi bemor uchun majburiy.")

        doctor, day, slot = data.get("doctor"), data.get("date"), data.get("time")
        if doctor and day and slot and slot not in doctor.get_available_slots(day):
            self.add_error("time", "Bu vaqt band yoki mavjud emas. Boshqa vaqtni tanlang.")
        return data        