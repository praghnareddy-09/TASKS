from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import User
from trainees.models import Trainee


@receiver(post_save, sender=get_user_model())
def create_trainee_profile(sender, instance, created, **kwargs):
    if instance.role == User.Role.TRAINEE:
        Trainee.objects.get_or_create(user=instance)
    elif not created:
        Trainee.objects.filter(user=instance).delete()
