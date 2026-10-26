from django.contrib.auth import views as auth_views
from django.urls import path
from . import notification_views


from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('doctors/', views.doctor_list, name='doctor_list'),
    path('doctors/<int:pk>/', views.doctor_detail, name='doctor_detail'),
    path('doctors/<int:pk>/slots/', views.doctor_slots, name='doctor_slots'),
    path('doctors/<int:pk>/book/', views.book_appointment, name='book'),
    path('appointments/', views.my_appointments, name='my_appointments'),
    path('appointments/<int:pk>/cancel/', views.cancel_appointment, name='cancel'),

    path('register/', views.register, name='register'),
    path('login/', views.RoleLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    path('notifications/', notification_views.notification_list, name='notifications'),
    path('notifications/count/', notification_views.notification_count, name='notifications_count'),
    path('notifications/read-all/', notification_views.notification_read_all, name='notifications_read_all'),
    path('notifications/<int:pk>/open/', notification_views.notification_open, name='notification_open'),
    path('password/change/', views.PasswordChangeView.as_view(), name='password_change'),
    path('profile/', views.profile, name='profile'),
]