from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('clin_app.urls')),
    path('manage/', include('clin_app.panel_urls')),
    path('doctor/', include('clin_app.doctor_urls')),
    path('favicon.ico', RedirectView.as_view(url=settings.STATIC_URL + 'img/favicon.ico', permanent=True)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)