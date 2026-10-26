def notifications(request):
    user = request.user
    if user.is_authenticated:
        return {"unread_count": user.notifications.filter(is_read=False).count()}
    return {}