from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.http import HttpResponse

from .excel_import import ImportFileError, build_template, import_doctors

from .models import Appointment, Department, Doctor
from .panel_forms import DepartmentForm, DoctorForm, ScheduleFormSet, SpecialtyForm
from .views import _parse_date
from .notifications import notify_status_change
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse

from .models import Appointment, Department, Doctor, User
from .notifications import notify_booked, notify_status_change
from .panel_forms import (
    DepartmentForm, DoctorForm, ManualBookingForm, ScheduleFormSet, SpecialtyForm,
)

from urllib.parse import urlencode

from .stats import EXPORT_LIMIT, appointments_qs, build_stats, build_workbook, parse_range, presets

import logging
import secrets

from django.db.models import Count, Max, Q
from django.views.decorators.cache import never_cache


def hospital_admin_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not (user.is_hospital_admin or user.is_superuser):
            raise PermissionDenied
        if not user.hospital_id:
            messages.error(request, "Sizga kasalxona biriktirilmagan. Administrator bilan bog'laning.")
            return redirect("home")
        request.hospital = user.hospital
        return view(request, *args, **kwargs)
    return wrapper


@hospital_admin_required
def dashboard(request):
    S = Appointment.Status
    today = timezone.localdate()
    appts = Appointment.objects.filter(doctor__hospital=request.hospital)

    stats = {
        "today": appts.filter(date=today).exclude(status=S.CANCELLED).count(),
        "upcoming": appts.filter(date__gt=today, status__in=[S.PENDING, S.CONFIRMED]).count(),
        "doctors": Doctor.objects.filter(hospital=request.hospital, is_active=True).count(),
        "month_done": appts.filter(date__year=today.year, date__month=today.month, status=S.COMPLETED).count(),
        "month_no_show": appts.filter(date__year=today.year, date__month=today.month, status=S.NO_SHOW).count(),
    }
    today_list = (
        appts.filter(date=today)
        .select_related("patient", "doctor__user", "doctor__specialty")
        .order_by("time")
    )
    return render(request, "panel/dashboard.html", {"stats": stats, "today_list": today_list})


@hospital_admin_required
def doctors(request):
    items = (
        Doctor.objects.filter(hospital=request.hospital)
        .select_related("user", "specialty", "department")
        .order_by("-is_active", "user__first_name")
    )
    return render(request, "panel/doctors.html", {"doctors": items})


@hospital_admin_required
def doctor_form(request, pk=None):
    doctor = get_object_or_404(Doctor, pk=pk, hospital=request.hospital) if pk else None
    form = DoctorForm(
        request.POST or None, request.FILES or None,
        instance=doctor, hospital=request.hospital,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            saved = form.save()
        if pk:
            messages.success(request, "Shifokor ma'lumotlari saqlandi.")
            return redirect("panel_doctors")
        messages.success(request, "Shifokor qo'shildi. Endi ish jadvalini belgilang.")
        return redirect("panel_doctor_schedule", pk=saved.pk)
    return render(request, "panel/doctor_form.html", {"form": form, "doctor": doctor})


@hospital_admin_required
def doctor_schedule(request, pk):
    doctor = get_object_or_404(Doctor, pk=pk, hospital=request.hospital)
    formset = ScheduleFormSet(request.POST or None, instance=doctor)
    if request.method == "POST" and formset.is_valid():
        formset.save()
        messages.success(request, "Ish jadvali saqlandi.")
        return redirect("panel_doctors")
    return render(request, "panel/schedule.html", {"doctor": doctor, "formset": formset})


@hospital_admin_required
@require_POST
def doctor_toggle(request, pk):
    doctor = get_object_or_404(Doctor, pk=pk, hospital=request.hospital)
    doctor.is_active = not doctor.is_active
    doctor.save(update_fields=["is_active"])
    messages.success(
        request,
        "Shifokor faollashtirildi." if doctor.is_active else "Shifokor faolsizlantirildi: saytda ko'rinmaydi.",
    )
    return redirect("panel_doctors")


@hospital_admin_required
def appointments(request):
    today = timezone.localdate()
    date_str = request.GET.get("date", today.isoformat())
    doctor_id = request.GET.get("doctor", "")
    status = request.GET.get("status", "")

    qs = Appointment.objects.filter(doctor__hospital=request.hospital).select_related(
        "patient", "doctor__user", "doctor__specialty"
    )
    day = _parse_date(date_str)
    if day:
        qs = qs.filter(date=day)
    if doctor_id.isdigit():
        qs = qs.filter(doctor_id=doctor_id)
    if status in Appointment.Status.values:
        qs = qs.filter(status=status)

    return render(request, "panel/appointments.html", {
        "appointments": qs.order_by("date", "time")[:300],
        "doctors": Doctor.objects.filter(hospital=request.hospital).select_related("user"),
        "statuses": Appointment.Status.choices,
        "date_value": date_str,
        "sel_doctor": doctor_id,
        "sel_status": status,
    })


@hospital_admin_required
@require_POST
def appointment_status(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk, doctor__hospital=request.hospital)
    old_status = appointment.status
    new_status = request.POST.get("status")
    allowed = {
        Appointment.Status.CONFIRMED, Appointment.Status.COMPLETED,
        Appointment.Status.CANCELLED, Appointment.Status.NO_SHOW,
    }
    if new_status in allowed and new_status != old_status:
        appointment.status = new_status
        appointment.save(update_fields=["status"])
        notify_status_change(appointment, old_status, request.user)
        messages.success(request, f"Holat o'zgartirildi: {appointment.get_status_display()}.")

    nxt = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = reverse("panel_appointments")
    return redirect(nxt)


@hospital_admin_required
def settings_page(request):
    hospital = request.hospital
    dep_form = DepartmentForm(prefix="dep")
    spec_form = SpecialtyForm(prefix="spec")

    if request.method == "POST":
        kind = request.POST.get("kind")
        if kind == "department":
            dep_form = DepartmentForm(request.POST, prefix="dep")
            if dep_form.is_valid():
                dep = dep_form.save(commit=False)
                dep.hospital = hospital
                dep.save()
                messages.success(request, "Bo'lim qo'shildi.")
                return redirect("panel_settings")
        elif kind == "specialty":
            spec_form = SpecialtyForm(request.POST, prefix="spec")
            if spec_form.is_valid():
                spec_form.save()
                messages.success(request, "Mutaxassislik qo'shildi.")
                return redirect("panel_settings")

    from .models import Specialty
    return render(request, "panel/settings.html", {
        "departments": Department.objects.filter(hospital=hospital),
        "specialties": Specialty.objects.all(),
        "dep_form": dep_form,
        "spec_form": spec_form,
    })


@hospital_admin_required
@require_POST
def department_delete(request, pk):
    get_object_or_404(Department, pk=pk, hospital=request.hospital).delete()
    messages.success(request, "Bo'lim o'chirildi.")
    return redirect("panel_settings")

@hospital_admin_required
def doctors_import(request):
    result = None
    if request.method == "POST":
        upload = request.FILES.get("file")
        if not upload:
            messages.error(request, "Fayl tanlanmadi.")
        elif not upload.name.lower().endswith(".xlsx"):
            messages.error(request, "Faqat .xlsx formatidagi fayl qabul qilinadi. Eski .xls bo'lsa, «Boshqacha saqlash» orqali .xlsx qiling.")
        elif upload.size > 2 * 1024 * 1024:
            messages.error(request, "Fayl hajmi 2 MB dan oshmasligi kerak.")
        else:
            try:
                result = import_doctors(upload, request.hospital)
            except ImportFileError as exc:
                messages.error(request, str(exc))
            else:
                if result["created"]:
                    messages.success(request, f"{len(result['created'])} ta shifokor qo'shildi.")
                elif not result["errors"]:
                    messages.error(request, "Faylda shifokor ma'lumotlari topilmadi.")
    return render(request, "panel/doctors_import.html", {"result": result})


@hospital_admin_required
def doctors_template(request):
    response = HttpResponse(
        build_template().getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="shifokorlar_shablon.xlsx"'
    return response

def _get_or_create_patient(form):
    if form.patient:
        return form.patient

    last9 = form.last9
    username, n = f"p{last9}", 1
    while User.objects.filter(username=username).exists():
        n += 1
        username = f"p{last9}_{n}"

    user = User(
        username=username,
        first_name=form.cleaned_data["first_name"],
        last_name=form.cleaned_data["last_name"],
        phone=f"+998{last9}",
        role=User.Role.PATIENT,
    )
    user.set_unusable_password()
    user.save()
    return user


@hospital_admin_required
def appointment_add(request):
    initial = {}
    if request.GET.get("doctor", "").isdigit():
        initial["doctor"] = request.GET["doctor"]

    form = ManualBookingForm(request.POST or None, hospital=request.hospital, initial=initial)

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            with transaction.atomic():
                patient = _get_or_create_patient(form)
                appointment = Appointment.objects.create(
                    patient=patient, doctor=data["doctor"],
                    date=data["date"], time=data["time"],
                    complaint=data["complaint"].strip(),
                )
        except IntegrityError:
            messages.error(request, "Afsuski, bu vaqt hozirgina band qilindi. Boshqa vaqtni tanlang.")
        else:
            notify_booked(appointment)
            messages.success(
                request,
                f"{patient.get_full_name() or patient.username} uchun qabul qo'shildi: "
                f"{appointment.date:%d.%m.%Y} soat {appointment.time:%H:%M}.",
            )
            return redirect("panel_appointments")

    return render(request, "panel/appointment_add.html", {
        "form": form,
        "today": timezone.localdate().isoformat(),
    })


@hospital_admin_required
def doctor_slots_json(request, pk):
    doctor = get_object_or_404(Doctor, pk=pk, hospital=request.hospital, is_active=True)
    day = _parse_date(request.GET.get("date"))
    slots = doctor.get_available_slots(day) if day else []
    return JsonResponse({"slots": [t.strftime("%H:%M") for t in slots]})


def _stats_params(request):
    start, end = parse_range(request.GET)
    raw = request.GET.get("doctor", "")
    return start, end, raw, (int(raw) if raw.isdigit() else None)


@hospital_admin_required
def stats(request):
    hospital = request.hospital
    start, end, raw, doctor_id = _stats_params(request)
    data = build_stats(hospital, start, end, doctor_id)

    extra = {"doctor": doctor_id} if doctor_id else {}
    query = urlencode({"from": start.isoformat(), "to": end.isoformat(), **extra})
    preset_links = [
        (label, urlencode({"from": a.isoformat(), "to": b.isoformat(), **extra}))
        for label, a, b in presets()
    ]

    return render(request, "panel/stats.html", {
        **data,
        "start": start, "end": end, "query": query, "presets": preset_links,
        "doctors": Doctor.objects.filter(hospital=hospital).select_related("user"),
        "sel_doctor": raw,
    })


@hospital_admin_required
def stats_export(request):
    hospital = request.hospital
    start, end, raw, doctor_id = _stats_params(request)
    data = build_stats(hospital, start, end, doctor_id)
    rows = (
        appointments_qs(hospital, start, end, doctor_id)
        .select_related("patient", "doctor__user", "doctor__specialty")
        .order_by("date", "time")[:EXPORT_LIMIT]
    )
    buffer = build_workbook(data, rows, start, end)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="statistika_{start}_{end}.xlsx"'
    return response

logger = logging.getLogger(__name__)
TEMP_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # o/0, l/1/I yo'q


def _hospital_patients(hospital):
    mine = Q(appointments__doctor__hospital=hospital)
    return (
        User.objects.filter(role=User.Role.PATIENT, is_superuser=False)
        .annotate(
            visits=Count("appointments", filter=mine),
            last_visit=Max("appointments__date", filter=mine),
        )
        .filter(visits__gt=0)
    )


@hospital_admin_required
def patients(request):
    q = request.GET.get("q", "").strip()
    qs = _hospital_patients(request.hospital)
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q)
            | Q(phone__icontains=q) | Q(username__icontains=q)
        )
    return render(request, "panel/patients.html", {"patients": qs.order_by("-last_visit")[:300], "q": q})


@hospital_admin_required
@require_POST
@never_cache
def patient_reset_password(request, pk):
    patient = get_object_or_404(_hospital_patients(request.hospital), pk=pk)
    temp = "".join(secrets.choice(TEMP_ALPHABET) for _ in range(8))

    patient.set_password(temp)
    patient.must_change_password = True
    patient.save(update_fields=["password", "must_change_password"])
    logger.warning("Parol tiklandi: admin_id=%s bemor_id=%s", request.user.pk, patient.pk)

    return render(request, "panel/patient_password.html", {"patient": patient, "temp": temp})