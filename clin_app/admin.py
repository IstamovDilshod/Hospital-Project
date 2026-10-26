from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Appointment, Department, Doctor, Hospital, Review,
    Specialty, TimeOff, User, WorkSchedule,
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "get_full_name", "role", "phone", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("username", "first_name", "last_name", "phone")
    fieldsets = UserAdmin.fieldsets + (
        ("Qo'shimcha", {"fields": ("role", "phone", "birth_date", "hospital")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Qo'shimcha", {"fields": ("role", "phone", "first_name", "last_name")}),
    )


class DepartmentInline(admin.TabularInline):
    model = Department
    extra = 1


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "phone", "is_active")
    search_fields = ("name", "address")
    inlines = [DepartmentInline]


admin.site.register(Specialty)


class WorkScheduleInline(admin.TabularInline):
    model = WorkSchedule
    extra = 1


class TimeOffInline(admin.TabularInline):
    model = TimeOff
    extra = 0


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("user", "specialty", "hospital", "price", "slot_minutes", "is_active")
    list_filter = ("hospital", "specialty", "is_active")
    search_fields = ("user__first_name", "user__last_name")
    inlines = [WorkScheduleInline, TimeOffInline]


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("patient", "doctor", "date", "time", "status")
    list_filter = ("status", "date", "doctor__hospital")
    search_fields = ("patient__first_name", "patient__last_name", "patient__phone")
    date_hierarchy = "date"


admin.site.register(Review)
# Register your models here.
