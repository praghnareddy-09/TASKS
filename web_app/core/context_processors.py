from placements.models import WorkflowNotification


def workflow_notifications(request):
    if not request.user.is_authenticated:
        return {"unread_workflow_notification_count": 0}
    return {
        "unread_workflow_notification_count": WorkflowNotification.objects.filter(
            recipient=request.user,
            read_at__isnull=True,
        ).count()
    }
