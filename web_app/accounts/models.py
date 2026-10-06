from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class TweakTechUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields["role"] = self.model.Role.ADMIN
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        TRAINEE = "TRAINEE", "Trainee"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.TRAINEE, db_index=True)
    is_approved = models.BooleanField(default=True)
    must_change_password = models.BooleanField(default=False)
    objects = TweakTechUserManager()

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="unique_nonempty_user_email_ci",
            )
        ]

    @property
    def is_admin_role(self):
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def is_trainee_role(self):
        return not self.is_superuser and self.role == self.Role.TRAINEE

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        if not self.is_approved:
            self.is_active = False
        super().save(*args, **kwargs)

    def __str__(self):
        return self.get_full_name() or self.username
