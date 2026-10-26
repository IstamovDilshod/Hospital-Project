from django.urls import path

from . import doctor_views as v

urlpatterns = [
    path("", v.dashboard, name="dpanel_dashboard"),
    path("appointments/", v.appointments, name="dpanel_appointments"),
    path("appointments/<int:pk>/", v.appointment_detail, name="dpanel_appointment"),
    path("appointments/<int:pk>/status/", v.appointment_status, name="dpanel_appointment_status"),
    path("patients/", v.patients, name="dpanel_patients"),
    path("patients/<int:pk>/", v.patient_detail, name="dpanel_patient"),
    path("timeoff/", v.timeoff, name="dpanel_timeoff"),
    path("timeoff/<int:pk>/delete/", v.timeoff_delete, name="dpanel_timeoff_delete"),
]