from django.shortcuts import redirect


class ForcePasswordChangeMiddleware:
    allowed_view_names = {
        "accounts:password_change",
        "accounts:password_change_done",
        "accounts:logout",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = request.user
        if request.path_info.startswith("/static/") or request.path_info in {"/sw.js", "/offline/"}:
            return None
        if (
            user.is_authenticated
            and user.must_change_password
            and request.resolver_match
            and request.resolver_match.view_name not in self.allowed_view_names
        ):
            return redirect("accounts:password_change")
        return None
