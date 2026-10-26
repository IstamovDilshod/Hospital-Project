from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .models import Notification


@login_required
def notification_list(request):
    items = request.user.notifications.all()[:50]
    return render(request, "notifications/list.html", {"items": items})


@login_required
def notification_open(request, pk):
    item = get_object_or_404(Notification, pk=pk, user=request.user)
    if not item.is_read:
        item.is_read = True
        item.save(update_fields=["is_read"])
    if item.url and url_has_allowed_host_and_scheme(item.url, allowed_hosts={request.get_host()}):
        return redirect(item.url)
    return redirect("notifications")


@login_required
@require_POST
def notification_read_all(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect("notifications")


@require_GET
def notification_count(request):
    if not request.user.is_authenticated:
        return JsonResponse({"count": 0})
    return JsonResponse({"count": request.user.notifications.filter(is_read=False).count()})