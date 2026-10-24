from functools import wraps

from flask import g, jsonify, redirect, request, session

from .models import db, User


def load_current_user():
    """Resolve the logged-in user from the signed session cookie."""
    user_id = session.get('user_id')
    g.user = db.session.get(User, user_id) if user_id else None
    if user_id and g.user is None:
        session.clear()


def _wants_json():
    return request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            if _wants_json():
                return jsonify({'success': False, 'message': 'Not logged in'}), 401
            return redirect('/login')
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not g.user.is_admin:
            if _wants_json():
                return jsonify({'success': False, 'message': 'Admin access required'}), 403
            return 'Admin access required', 403
        return view(*args, **kwargs)
    return wrapped
