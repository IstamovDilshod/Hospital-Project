from datetime import date as date_cls, datetime

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.auth import views as auth_views
from django.urls import reverse

from .forms import RegisterForm
from .models import Appointment, Doctor, Hospital, Specialty, User
from .notifications import notify_booked, notify_cancelled
from .booking_rules import LEAD_MINUTES, can_cancel, check_patient_limits, max_date
from django.urls import reverse_lazy
from .forms import ProfileForm, RegisterForm

def home(request):
    context = {
        'specialties': Specialty.objects.all(),
        'doctors': Doctor.objects.filter(is_active=True).select_related('user', 'specialty', 'hospital')[:6],
    }
    return render(request, 'home.html', context)


def doctor_list(request):
    doctors = Doctor.objects.filter(is_active=True).select_related('user', 'specialty', 'hospital')

    q = request.GET.get('q', '').strip()
    specialty = request.GET.get('specialty', '')
    hospital = request.GET.get('hospital', '')

    if q:
        doctors = doctors.filter(
            Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q)
        )
    if specialty:
        doctors = doctors.filter(specialty_id=specialty)
    if hospital:
        doctors = doctors.filter(hospital_id=hospital)

    context = {
        'doctors': doctors,
        'specialties': Specialty.objects.all(),
        'hospitals': Hospital.objects.filter(is_active=True),
        'q': q,
        'selected_specialty': specialty,
        'selected_hospital': hospital,
    }
    return render(request, 'doctors/list.html', context)


def doctor_detail(request, pk):
    doctor = get_object_or_404(
        Doctor.objects.select_related('user', 'specialty', 'hospital'), pk=pk, is_active=True
    )
    context = {
        'doctor': doctor,
        'today': timezone.localdate().isoformat(),
        'max_date': max_date().isoformat(),
        'schedules': doctor.schedules.all(),

    }
    return render(request, 'doctors/detail.html', context)


def _parse_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def doctor_slots(request, pk):
    """HTMX uchun: tanlangan kunning bo'sh vaqtlarini qaytaradi."""
    doctor = get_object_or_404(Doctor, pk=pk, is_active=True)
    day = _parse_date(request.GET.get('date'))
    ok_day = day and day <= max_date()
    slots = doctor.get_available_slots(day, lead_minutes=LEAD_MINUTES) if ok_day else []
    return render(request, 'doctors/_slots.html', {
        'doctor': doctor, 'slots': slots, 'day': day,
    })


@login_required
@require_POST
def book_appointment(request, pk):
    doctor = get_object_or_404(Doctor, pk=pk, is_active=True)

    if not request.user.is_patient:
        messages.error(request, "Faqat bemorlar qabulga yozilishi mumkin.")
        return redirect('doctor_detail', pk=pk)

    day = _parse_date(request.POST.get('date'))
    try:
        slot_time = datetime.strptime(request.POST.get('time', ''), '%H:%M').time()
    except ValueError:
        slot_time = None

    available = doctor.get_available_slots(day, lead_minutes=LEAD_MINUTES) if day else []
    if not day or not slot_time or slot_time not in available:
        messages.error(request, "Bu vaqt band yoki mavjud emas. Boshqa vaqtni tanlang.")
        return redirect('doctor_detail', pk=pk)

    problem = check_patient_limits(request.user, doctor, day, slot_time)
    if problem:
        messages.error(request, problem)
        return redirect('doctor_detail', pk=pk)

    try:
        with transaction.atomic():
            appointment = Appointment.objects.create(
                patient=request.user,
                doctor=doctor,
                date=day,
                time=slot_time,
                complaint=request.POST.get('complaint', '').strip(),
            )
    except IntegrityError:
        # ikki bemor bir vaqtda bosgan holat
        messages.error(request, "Afsuski, bu vaqtni boshqa bemor band qilib bo'ldi.")
        return redirect('doctor_detail', pk=pk)

    notify_booked(appointment)
    messages.success(request, f"Siz {day:%d.%m.%Y} kuni soat {slot_time:%H:%M} ga yozildingiz.")
    return redirect('my_appointments')


@login_required
def my_appointments(request):
    appointments = list(
        Appointment.objects.filter(patient=request.user)
        .select_related('doctor__user', 'doctor__specialty', 'doctor__hospital')
    )
    for a in appointments:
        a.can_cancel, a.cancel_note = can_cancel(a)
    return render(request, 'appointments/list.html', {'appointments': appointments})


@login_required
@require_POST
def cancel_appointment(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk, patient=request.user)
    ok, note = can_cancel(appointment)
    if ok:
        appointment.status = Appointment.Status.CANCELLED
        appointment.save(update_fields=['status'])
        notify_cancelled(appointment, request.user)
        messages.success(request, "Qabul bekor qilindi.")
    elif note:
        messages.error(request, note)
    return redirect('my_appointments')



def register(request):
    if request.user.is_authenticated:
        return redirect('home')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Ro'yxatdan muvaffaqiyatli o'tdingiz!")
        return redirect('home')
    return render(request, 'auth/register.html', {'form': form})


class RoleLoginView(auth_views.LoginView):
    template_name = 'auth/login.html'
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        user = self.request.user
        if user.is_hospital_admin:
            return reverse('panel_dashboard')
        if user.is_doctor:
            return reverse('dpanel_dashboard')
        return super().get_default_redirect_url()


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = 'auth/password_change.html'
    success_url = reverse_lazy('home')

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        if user.must_change_password:
            user.must_change_password = False
            user.save(update_fields=['must_change_password'])
        messages.success(self.request, "Parol muvaffaqiyatli almashtirildi.")
        return response

@login_required
def profile(request):
    # Yangi nusxa: forma xato bo'lsa, navbar'dagi ism o'zgarib ketmasligi uchun
    me = User.objects.get(pk=request.user.pk)
    form = ProfileForm(request.POST or None, instance=me)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Ma'lumotlaringiz saqlandi.")
        return redirect('profile')
    return render(request, 'profile.html', {'form': form, 'me': me})