from flask import Blueprint, g, jsonify, redirect, render_template, request
from werkzeug.security import generate_password_hash

from .auth import admin_required
from .models import db, File, User
from .views import MIN_PASSWORD_LEN, _int_arg, remove_from_disk, utc_iso

bp = Blueprint('admin', __name__)


@bp.route('/admin')
@admin_required
def dashboard():
    return render_template('admin.htm')


@bp.route('/admin/users-page')
def users_page():
    return redirect('/admin')


@bp.route('/admin/files')
@admin_required
def user_files():
    user = db.session.get(User, _int_arg(request.args.get('user_id')) or 0)
    if not user:
        return 'User not found', 404
    files = sorted(user.files, key=lambda f: f.id, reverse=True)
    return render_template('admin_files.htm', user=user, files=files)


@bp.route('/api/admin/users')
@admin_required
def list_users():
    users = User.query.order_by(User.username).all()
    return jsonify({'success': True, 'users': [
        {'user_id': u.id, 'username': u.username, 'is_admin': bool(u.is_admin),
         'is_self': u.id == g.user.id, 'created_at': utc_iso(u.created_at),
         'dataset_count': len(u.datasets), 'file_count': len(u.files)}
        for u in users]})


@bp.route('/api/admin/reset_password', methods=['POST'])
@admin_required
def reset_password():
    user = db.session.get(User, _int_arg(request.form.get('user_id')) or 0)
    if not user:
        return jsonify({'success': False, 'message': 'The user does not exist.'}), 404
    password = request.form.get('password') or ''
    if len(password) < MIN_PASSWORD_LEN:
        return jsonify({'success': False,
                        'message': f'Password must be at least {MIN_PASSWORD_LEN} characters'}), 400
    user.password = generate_password_hash(password)
    db.session.commit()
    return jsonify({'success': True, 'message': f'Password for {user.username} has been reset.'})


@bp.route('/api/admin/delete_user', methods=['POST'])
@admin_required
def delete_user():
    user = db.session.get(User, _int_arg(request.form.get('user_id')) or 0)
    if not user:
        return jsonify({'success': False, 'message': 'The user does not exist.'}), 404
    if user.id == g.user.id:
        return jsonify({'success': False, 'message': 'You cannot delete your own account.'}), 400
    remove_from_disk(File.query.filter_by(user_id=user.id).all())
    db.session.delete(user)
    db.session.commit()
    return jsonify({'success': True, 'message': 'The user and their files have been deleted.'})
