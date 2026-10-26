from django.urls import path

from . import panel_views as v

urlpatterns = [
    path("", v.dashboard, name="panel_dashboard"),
    path("doctors/", v.doctors, name="panel_doctors"),
    path("doctors/add/", v.doctor_form, name="panel_doctor_add"),
    path("doctors/import/", v.doctors_import, name="panel_doctors_import"),
    path("doctors/template/", v.doctors_template, name="panel_doctors_template"),
    path("doctors/<int:pk>/edit/", v.doctor_form, name="panel_doctor_edit"),
    path("doctors/<int:pk>/schedule/", v.doctor_schedule, name="panel_doctor_schedule"),
    path("doctors/<int:pk>/toggle/", v.doctor_toggle, name="panel_doctor_toggle"),
    path("appointments/", v.appointments, name="panel_appointments"),
    path("appointments/<int:pk>/status/", v.appointment_status, name="panel_appointment_status"),
    path("appointments/add/", v.appointment_add, name="panel_appointment_add"),
    path("stats/", v.stats, name="panel_stats"),
    path("stats/export/", v.stats_export, name="panel_stats_export"),
    path("doctors/<int:pk>/slots/", v.doctor_slots_json, name="panel_doctor_slots"),
    path("settings/", v.settings_page, name="panel_settings"),
    path("settings/departments/<int:pk>/delete/", v.department_delete, name="panel_department_delete"),
        path("patients/", v.patients, name="panel_patients"),
    path("patients/<int:pk>/reset-password/", v.patient_reset_password, name="panel_patient_reset"),
]