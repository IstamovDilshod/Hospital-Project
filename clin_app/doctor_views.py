from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Max, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .doctor_forms import TimeOffForm
from .models import Appointment, TimeOff, User, WorkSchedule
from .views import _parse_date
from .notifications import notify_status_change

S = Appointment.Status
WAITING = [S.PENDING, S.CONFIRMED]
ACTIVE = [S.PENDING, S.CONFIRMED, S.COMPLETED, S.NO_SHOW]


def doctor_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not user.is_doctor:
            raise PermissionDenied
        doctor = getattr(user, "doctor_profile", None)
        if doctor is None:
            messages.error(request, "Sizning akkauntingizga shifokor profili biriktirilmagan.")
            return redirect("home")
        request.doctor = doctor
        return view(request, *args, **kwargs)
    return wrapper


def _age(birth, today):
    if not birth:
        return None
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


@doctor_required
def dashboard(request):
    today = timezone.localdate()
    base = Appointment.objects.filter(doctor=request.doctor)
    today_list = (
        base.filter(date=today).exclude(status=S.CANCELLED)
        .select_related("patient").order_by("time")
    )
    stats = {
        "total": today_list.count(),
        "waiting": today_list.filter(status__in=WAITING).count(),
        "done": today_list.filter(status=S.COMPLETED).count(),
        "no_show": today_list.filter(status=S.NO_SHOW).count(),
        "upcoming": base.filter(date__gt=today, status__in=WAITING).count(),
    }
    return render(request, "dpanel/dashboard.html", {
        "today_list": today_list,
        "stats": stats,
        "next_appt": today_list.filter(status__in=WAITING).first(),
        "today": today,
    })


@doctor_required
def appointments(request):
    today = timezone.localdate()
    date_str = request.GET.get("date", today.isoformat())
    status = request.GET.get("status", "")

    qs = Appointment.objects.filter(doctor=request.doctor).select_related("patient")
    day = _parse_date(date_str)
    if day:
        qs = qs.filter(date=day)
    if status in S.values:
        qs = qs.filter(status=status)

    return render(request, "dpanel/appointments.html", {
        "appointments": qs.order_by("date", "time")[:300],
        "statuses": S.choices,
        "date_value": date_str,
        "sel_status": status,
    })


@doctor_required
def appointment_detail(request, pk):
    appt = get_object_or_404(
        Appointment.objects.select_related("patient"), pk=pk, doctor=request.doctor
    )

    if request.method == "POST":
        appt.doctor_note = request.POST.get("doctor_note", "").strip()[:5000]
        fields = ["doctor_note"]
        if "finish" in request.POST and appt.status in WAITING:
            appt.status = S.COMPLETED
            fields.append("status")
        appt.save(update_fields=fields)
        messages.success(request, "Saqlandi.")
        return redirect("dpanel_appointment", pk=appt.pk)

    history = (
        Appointment.objects.filter(doctor=request.doctor, patient=appt.patient)
        .exclude(pk=appt.pk).order_by("-date", "-time")[:20]
    )
    return render(request, "dpanel/appointment_detail.html", {
        "appt": appt,
        "history": history,
        "age": _age(appt.patient.birth_date, timezone.localdate()),
    })


@doctor_required
@require_POST
def appointment_status(request, pk):
    appt = get_object_or_404(Appointment, pk=pk, doctor=request.doctor)
    old_status = appt.status
    new_status = request.POST.get("status")
    if new_status in {S.CONFIRMED, S.COMPLETED, S.NO_SHOW, S.CANCELLED} and new_status != old_status:
        appt.status = new_status
        appt.save(update_fields=["status"])
        notify_status_change(appt, old_status, request.user)
        messages.success(request, f"Holat o'zgartirildi: {appt.get_status_display()}.")

    nxt = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = reverse("dpanel_dashboard")
    return redirect(nxt)


@doctor_required
def patients(request):
    q = request.GET.get("q", "").strip()
    mine = Q(appointments__doctor=request.doctor, appointments__status__in=ACTIVE)
    qs = User.objects.annotate(
        visits=Count("appointments", filter=mine),
        last_visit=Max("appointments__date", filter=mine),
    ).filter(visits__gt=0)
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(phone__icontains=q)
        )
    return render(request, "dpanel/patients.html", {
        "patients": qs.order_by("-last_visit")[:300], "q": q,
    })


@doctor_required
def patient_detail(request, pk):
    patient = get_object_or_404(User, pk=pk, role=User.Role.PATIENT)
    visits = (
        Appointment.objects.filter(doctor=request.doctor, patient=patient)
        .order_by("-date", "-time")
    )
    if not visits.exists():
        raise Http404
    return render(request, "dpanel/patient_detail.html", {
        "patient": patient,
        "visits": visits,
        "age": _age(patient.birth_date, timezone.localdate()),
    })


@doctor_required
def timeoff(request):
    doctor = request.doctor
    today = timezone.localdate()
    form = TimeOffForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        off = form.save(commit=False)
        off.doctor = doctor
        off.save()
        conflicts = Appointment.objects.filter(
            doctor=doctor, date__range=(off.start_date, off.end_date), status__in=WAITING
        ).count()
        if conflicts:
            messages.error(
                request,
                f"Dam olish qo'shildi, lekin shu oraliqda {conflicts} ta faol qabul bor. "
                "Ularni «Qabullar» bo'limida bekor qiling yoki bemorlar bilan kelishing.",
            )
        else:
            messages.success(request, "Dam olish kunlari qo'shildi. Shu kunlarda yozilish yopiq.")
        return redirect("dpanel_timeoff")

    by_day = {}
    for item in doctor.schedules.all():
        by_day.setdefault(item.weekday, []).append(item)
    week = [(label, by_day.get(value, [])) for value, label in WorkSchedule.Weekday.choices]

    return render(request, "dpanel/timeoff.html", {
        "form": form,
        "time_offs": doctor.time_offs.filter(end_date__gte=today).order_by("start_date"),
        "week": week,
    })


@doctor_required
@require_POST
def timeoff_delete(request, pk):
    get_object_or_404(TimeOff, pk=pk, doctor=request.doctor).delete()
    messages.success(request, "Dam olish o'chirildi.")
    return redirect("dpanel_timeoff")