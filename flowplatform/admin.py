from flask import Blueprint, g, jsonify, redirect, render_template, request

from .auth import admin_required
from .models import db, File, User
from .views import _int_arg, remove_from_disk

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
    return render_template('admin_files.htm', user=user, files=user.files)


@bp.route('/api/admin/users')
@admin_required
def list_users():
    users = User.query.order_by(User.username).all()
    return jsonify({'success': True, 'users': [
        {'user_id': u.id, 'username': u.username, 'is_admin': bool(u.is_admin),
         'files': [{'file_id': f.id, 'file_name': f.file_name} for f in u.files]}
        for u in users]})


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
