import os
import re
from datetime import datetime, timezone

from flask import (Blueprint, current_app, g, jsonify, redirect, render_template, request, send_file,
                   session)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from . import analysis
from .auth import login_required
from .models import db, Batch, Dataset, File, User
from .reports import batch_report_pdf

bp = Blueprint('main', __name__)

# Usernames are rendered into admin pages, so keep them to a safe character set.
USERNAME_RE = re.compile(r'[A-Za-z0-9_.-]{3,50}')
MIN_PASSWORD_LEN = 6


# ---------- helpers ----------

def _int_arg(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_arg(value):
    try:
        return float(value) if value not in (None, '') else None
    except ValueError:
        return None


def utc_iso(dt):
    """ISO 8601 string for a stored UTC timestamp (SQLite drops the tzinfo), so browsers can show local time."""
    if dt is None:
        return ''
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def _error(message, status):
    return jsonify({'success': False, 'message': message}), status


def _own_dataset(dataset_id):
    return Dataset.query.filter_by(id=dataset_id, user_id=g.user.id).first() if dataset_id else None


def _own_batch(batch_id):
    batch = db.session.get(Batch, batch_id) if batch_id else None
    return batch if batch and batch.dataset.user_id == g.user.id else None


def _own_file(file_id):
    f = db.session.get(File, file_id) if file_id else None
    return f if f and f.user_id == g.user.id else None


def remove_from_disk(files):
    for f in files:
        try:
            os.remove(f.file_path)
        except OSError:
            pass


def _dataset_summary(user_id):
    result = []
    for dataset in Dataset.query.filter_by(user_id=user_id).all():
        result.append({
            'dataset_id': dataset.id,
            'dataset_name': dataset.dataset_name,
            'batches': [{'batch_id': b.id, 'batch_name': b.batch_name, 'samples': len(b.files)}
                        for b in dataset.batches],
        })
    return result


def _plot_path(file_id):
    return os.path.join(current_app.config['DATA_DIR'], 'plots', f'u{g.user.id}_f{file_id}.png')


# ---------- auth ----------

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.htm')
    user = User.query.filter_by(username=request.form.get('username', '')).first()
    if not user or not check_password_hash(user.password, request.form.get('password', '')):
        return jsonify({'success': False, 'message': 'Incorrect username or password'})
    session.clear()
    session['user_id'] = user.id
    return jsonify({'success': True, 'message': 'Login Successful',
                    'redirect': '/admin' if user.is_admin else '/', 'is_admin': bool(user.is_admin)})


@bp.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.htm')
    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    if not USERNAME_RE.fullmatch(username):
        return jsonify({'success': False, 'message': 'Username must be 3-50 letters, digits, ".", "_" or "-"'})
    if len(password) < MIN_PASSWORD_LEN:
        return jsonify({'success': False, 'message': f'Password must be at least {MIN_PASSWORD_LEN} characters'})
    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'Username already exists'})
    db.session.add(User(username=username, password=generate_password_hash(password)))
    db.session.commit()
    return jsonify({'success': True, 'message': 'Account created', 'redirect': '/login?registered=1'})


@bp.route('/api/check_auth')
@login_required
def check_auth():
    return jsonify({'success': True, 'user': {'id': g.user.id, 'username': g.user.username}})


# ---------- pages ----------

@bp.route('/')
@login_required
def user_datasets():
    return render_template('datasets.htm', dataset_list=_dataset_summary(g.user.id))


@bp.route('/edit')
@login_required
def edit_page():
    return render_template('edit.htm', dataset_list=_dataset_summary(g.user.id))


@bp.route('/scan')
@login_required
def scan_page():
    return render_template('scan.htm')


@bp.route('/batch')
@login_required
def list_batch():
    batch = _own_batch(_int_arg(request.args.get('batch_id')))
    if not batch:
        return 'Batch not found', 404
    batch_data = {
        'batch_id': batch.id,
        'batch_name': batch.batch_name,
        'files': [{'id': f.id, 'file_name': f.file_name, 'file_type': f.file_type,
                   'uploaded_at': f.uploaded_at.strftime('%Y-%m-%d %H:%M:%S') if f.uploaded_at else ''}
                  for f in batch.files],
    }
    return render_template('batch.htm', batch=batch_data)


@bp.route('/download_batch_report')
@login_required
def download_batch_report():
    batch = _own_batch(_int_arg(request.args.get('batch_id')))
    if not batch:
        return 'Batch not found', 404
    pdf = batch_report_pdf(batch, current_app.config['PANEL'])
    return send_file(pdf, mimetype='application/pdf', as_attachment=True,
                     download_name=f'batch_{secure_filename(batch.batch_name) or batch.id}_report.pdf')


# ---------- sample analysis ----------

@bp.route('/sample', methods=['GET'])
@login_required
def sample_page():
    f = _own_file(_int_arg(request.args.get('file_id')))
    if not f:
        return 'File not found', 404
    panel = current_app.config['PANEL']
    ch_list = analysis.channel_names(panel)
    return render_template('sample.htm',
                           file_id=f.id,
                           batch_id=f.batch_id,
                           sample_filename=os.path.splitext(f.file_name)[0],
                           ch_list=ch_list,
                           default_x=ch_list[8] if len(ch_list) > 8 else ch_list[0],
                           default_y=ch_list[9] if len(ch_list) > 9 else ch_list[3],
                           gates=panel['gates'])


@bp.route('/sample', methods=['PUT'])
@login_required
def sample_update():
    """Re-render the plot for the given settings and return the number of events inside the region."""
    f = _own_file(_int_arg(request.args.get('file_id')))
    if not f:
        return _error('File not found', 404)
    panel = current_app.config['PANEL']

    ch_x = request.args.get('ch_X', 'FSC-A')
    ch_y = request.args.get('ch_Y', 'SSC-A')
    x_scale = 'logicle' if request.args.get('ch_X_scale') == 'logicle' else 'linear'
    y_scale = 'logicle' if request.args.get('ch_Y_scale') == 'logicle' else 'linear'
    bounds = [_float_arg(request.args.get(k)) for k in ('x_min', 'x_max', 'y_min', 'y_max')]

    gate_id = _int_arg(request.args.get('gate_id'))
    gate = next((gt for gt in panel['gates'] if gt['gate_id'] == gate_id), None)
    if gate:
        ch_x, ch_y = gate['ch_X'], gate['ch_Y']

    try:
        x, y = analysis.load_channel_pair(f.file_path, panel, ch_x, ch_y, x_scale, y_scale)
    except ValueError as e:
        return _error(str(e), 400)
    except Exception as e:
        current_app.logger.exception('Failed to read %s', f.file_path)
        return _error(f'Could not read FCS file: {e}', 500)

    data_range = [x.min(), x.max(), y.min(), y.max()]
    if gate:
        polygon = analysis.gate_polygon(gate, x_scale, y_scale)
        limits = data_range
    else:
        limits = [b if b is not None else d for b, d in zip(bounds, data_range)]
        polygon = None
        if None not in bounds:
            x0, x1, y0, y1 = bounds
            polygon = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]

    count = analysis.count_in_polygon(x, y, polygon) if polygon is not None else int(len(x))

    fig = analysis.density_plot(x, y, ch_x, ch_y, x_scale, y_scale, limits=limits, polygon=polygon)
    out = _plot_path(f.id)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out)
    analysis.plt.close(fig)

    return jsonify({'cell_count': count, 'ch_X': ch_x, 'ch_Y': ch_y})


@bp.route('/sample/plot')
@login_required
def sample_plot():
    f = _own_file(_int_arg(request.args.get('file_id')))
    path = _plot_path(f.id) if f else None
    if not path or not os.path.isfile(path):
        return '', 404
    resp = send_file(path, mimetype='image/png')
    resp.headers['Cache-Control'] = 'no-store'
    return resp


# ---------- datasets / batches API ----------

@bp.route('/api/datasets')
@login_required
def get_datasets():
    return jsonify({'success': True, 'datasets': _dataset_summary(g.user.id)})


@bp.route('/api/dataset/new', methods=['POST'])
@login_required
def create_dataset():
    name = (request.form.get('dataset_name') or '').strip()
    if not name:
        return _error('Dataset name is required', 400)
    dataset = Dataset(user_id=g.user.id, dataset_name=name)
    db.session.add(dataset)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Dataset created successfully', 'dataset': {
        'dataset_id': dataset.id, 'dataset_name': dataset.dataset_name, 'batches': []}})


@bp.route('/api/dataset/delete', methods=['POST'])
@login_required
def delete_dataset():
    dataset = _own_dataset(_int_arg(request.form.get('dataset_id')))
    if not dataset:
        return _error('Dataset not found or not owned by user', 404)
    remove_from_disk([f for b in dataset.batches for f in b.files])
    db.session.delete(dataset)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Dataset deleted successfully'})


@bp.route('/api/batches')
@login_required
def get_batches():
    dataset = _own_dataset(_int_arg(request.args.get('dataset_id')))
    if not dataset:
        return _error('Dataset not found', 404)
    return jsonify({'success': True, 'batches': [{'batch_id': b.id, 'batch_name': b.batch_name}
                                                 for b in dataset.batches]})


@bp.route('/api/batch/new', methods=['POST'])
@login_required
def create_batch():
    dataset = _own_dataset(_int_arg(request.form.get('dataset_id')))
    if not dataset:
        return _error('Dataset not found or not owned by user', 404)
    name = (request.form.get('batch_name') or '').strip() or \
        'New Batch ' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    batch = Batch(dataset_id=dataset.id, batch_name=name)
    db.session.add(batch)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Batch created successfully', 'batch': {
        'batch_id': batch.id, 'batch_name': batch.batch_name, 'samples': []}})


@bp.route('/api/batch/delete', methods=['POST'])
@login_required
def delete_batch():
    batch = _own_batch(_int_arg(request.form.get('batch_id')))
    if not batch:
        return _error('Batch not found or not owned by user', 404)
    remove_from_disk(batch.files)
    db.session.delete(batch)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Batch deleted successfully'})


# ---------- uploads ----------

@bp.route('/api/uploads')
@login_required
def get_uploads():
    files = File.query.filter_by(user_id=g.user.id).all()
    return jsonify({'success': True, 'uploads': [
        {'filename': f.file_name,
         'upload_date': f.uploaded_at.strftime('%Y-%m-%d %H:%M:%S') if f.uploaded_at else ''}
        for f in files]})


@bp.route('/upload', methods=['POST'])
@login_required
def upload_file():
    upload = request.files.get('file')
    dataset = _own_dataset(_int_arg(request.form.get('dataset')))
    batch = _own_batch(_int_arg(request.form.get('batch')))
    if not upload or not upload.filename:
        return _error('No file selected', 400)
    if not dataset or not batch or batch.dataset_id != dataset.id:
        return _error('Dataset or batch not found', 404)

    filename = secure_filename(upload.filename)
    if not filename.lower().endswith('.fcs'):
        return _error('Only .fcs files are supported', 400)

    folder = os.path.join(current_app.config['DATA_DIR'], 'uploads', str(g.user.id), str(batch.id))
    os.makedirs(folder, exist_ok=True)
    stem, ext = os.path.splitext(filename)
    path, n = os.path.join(folder, filename), 1
    while os.path.exists(path):
        path = os.path.join(folder, f'{stem}_{n}{ext}')
        n += 1
    upload.save(path)

    db.session.add(File(batch_id=batch.id, user_id=g.user.id, file_name=os.path.basename(path),
                        file_type='FCS', file_path=path))
    db.session.commit()
    return jsonify({'success': True, 'message': 'File uploaded successfully', 'redirect': '/'})
