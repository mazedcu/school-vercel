from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages

def role_required(*allowed_roles):
    """
    Decorator to restrict view access to specific user roles.
    Assumes the view is also protected by @login_required.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.role not in allowed_roles and request.user.role != 'admin':
                messages.error(request, "You do not have permission to access this page.")
                return redirect('dashboard_router')
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
