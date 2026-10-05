from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        TRAINER = "TRAINER", "Trainer"
        TRAINEE = "TRAINEE", "Trainee"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.TRAINEE, db_index=True)

    def __str__(self):
        return self.get_full_name() or self.username
