from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from placements.models import (
    ApplicationInterview,
    JobApplication,
    WorkflowAudit,
    WorkflowNotification,
)


INTERVIEW_APPLICATION_STATUS = {
    ApplicationInterview.Status.INTERVIEW_SCHEDULED: JobApplication.Status.HR_ROUND,
    ApplicationInterview.Status.ASSESSMENT_COMPLETED: JobApplication.Status.ASSESSMENT,
    ApplicationInterview.Status.SHORTLISTED: JobApplication.Status.SHORTLISTED,
    ApplicationInterview.Status.SELECTED: JobApplication.Status.SELECTED,
    ApplicationInterview.Status.REJECTED: JobApplication.Status.REJECTED,
    ApplicationInterview.Status.OFFER_RELEASED: JobApplication.Status.OFFER_RECEIVED,
    ApplicationInterview.Status.JOINED: JobApplication.Status.JOINED,
}


def publish_workflow_event(trainee_id, event_type):
    def publish():
        channel_layer = get_channel_layer()
        payload = {"type": "workflow.changed", "event": event_type}
        async_to_sync(channel_layer.group_send)("workflow_admin", payload)
        async_to_sync(channel_layer.group_send)(f"workflow_trainee_{trainee_id}", payload)

    transaction.on_commit(publish)


def notify_workflow_users(trainee, event_type, message, actor, application=None):
    recipients = set(
        User.objects.filter(is_active=True, role=User.Role.ADMIN).exclude(email="").values_list("pk", flat=True)
    )
    recipients.add(trainee.user_id)
    WorkflowNotification.objects.bulk_create(
        [
            WorkflowNotification(
                recipient_id=recipient_id,
                trainee=trainee,
                application=application,
                event_type=event_type,
                message=message,
            )
            for recipient_id in recipients
            if recipient_id != getattr(actor, "pk", None)
        ]
    )
    publish_workflow_event(trainee.pk, event_type)


def record_status_change(*, trainee, application, actor, entity_type, entity_id, field_name, old_value, new_value):
    if old_value == new_value:
        return
    WorkflowAudit.objects.create(
        trainee=trainee,
        application=application,
        actor=actor,
        entity_type=entity_type,
        entity_id=entity_id,
        field_name=field_name,
        previous_value=old_value or "",
        new_value=new_value,
    )


@transaction.atomic
def save_interview_update(interview, actor):
    application = interview.application
    old_interview_status = interview.pk and (
        ApplicationInterview.objects.filter(pk=interview.pk).values_list("status", flat=True).first()
    )
    old_application_status = application.status
    interview.updated_by = actor
    interview.save()
    new_application_status = INTERVIEW_APPLICATION_STATUS[interview.status]
    application.status = new_application_status
    application.updated_at = timezone.now()
    application.save(update_fields=["status", "updated_at"])

    record_status_change(
        trainee=application.trainee,
        application=application,
        actor=actor,
        entity_type="interview",
        entity_id=interview.pk,
        field_name="status",
        old_value=old_interview_status,
        new_value=interview.status,
    )
    record_status_change(
        trainee=application.trainee,
        application=application,
        actor=actor,
        entity_type="application",
        entity_id=application.pk,
        field_name="status",
        old_value=old_application_status,
        new_value=application.status,
    )
    notify_workflow_users(
        application.trainee,
        "interview.updated",
        f"Interview status updated to {interview.get_status_display()} for {application.company_name}.",
        actor,
        application,
    )
    return interview


def application_status_updated(application, actor, old_status):
    record_status_change(
        trainee=application.trainee,
        application=application,
        actor=actor,
        entity_type="application",
        entity_id=application.pk,
        field_name="status",
        old_value=old_status,
        new_value=application.status,
    )
    notify_workflow_users(
        application.trainee,
        "application.updated",
        f"Application status is now {application.get_status_display()} for {application.company_name}.",
        actor,
        application,
    )
