from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from accounts.models import User


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles = ()

    def test_func(self):
        return self.request.user.role in self.allowed_roles or self.request.user.is_superuser


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = (User.Role.ADMIN,)


class TrainerRequiredMixin(RoleRequiredMixin):
    allowed_roles = (User.Role.ADMIN, User.Role.TRAINER)


class TraineeRequiredMixin(RoleRequiredMixin):
    allowed_roles = (User.Role.ADMIN, User.Role.TRAINER, User.Role.TRAINEE)
