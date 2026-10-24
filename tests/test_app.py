import io

import numpy as np
import pytest

from flowplatform import create_app
from flowplatform.analysis import count_in_polygon, gate_vertices
from flowplatform.models import db, User


@pytest.fixture
def app(tmp_path):
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test',
        'DATA_DIR': str(tmp_path),
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
    })
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def register_and_login(client, username='alice', password='secret123'):
    client.post('/register', data={'username': username, 'password': password})
    return client.post('/login', data={'username': username, 'password': password}).get_json()


def test_register_and_login(client):
    res = client.post('/register', data={'username': 'alice', 'password': 'secret123'}).get_json()
    assert res['success']
    assert client.post('/login', data={'username': 'alice', 'password': 'wrong'}).get_json()['success'] is False
    assert register_and_login(client)['success']


def test_home_shows_overview(client):
    register_and_login(client)
    ds = client.post('/api/dataset/new', data={'dataset_name': 'DS'}).get_json()['dataset']
    client.post('/api/batch/new', data={'dataset_id': ds['dataset_id'], 'batch_name': 'B1'})
    html = client.get('/').get_data(as_text=True)
    assert 'Welcome, alice' in html
    assert 'Recent batches' in html and 'B1' in html


def test_register_rejects_unsafe_username(client):
    res = client.post('/register', data={'username': '<script>', 'password': 'secret123'}).get_json()
    assert res['success'] is False


def test_api_requires_login(client):
    assert client.get('/api/datasets').status_code == 401
    # The old scheme trusted a user id in the Authorization header; that must not work anymore.
    assert client.get('/api/datasets', headers={'Authorization': '1'}).status_code == 401
    assert client.get('/').status_code == 302


def test_dataset_and_batch_lifecycle(client):
    register_and_login(client)
    ds = client.post('/api/dataset/new', data={'dataset_name': 'DS'}).get_json()['dataset']
    batch = client.post('/api/batch/new', data={'dataset_id': ds['dataset_id'], 'batch_name': 'B1'}).get_json()['batch']
    datasets = client.get('/api/datasets').get_json()['datasets']
    assert datasets[0]['batches'][0]['batch_name'] == 'B1'

    assert client.post('/api/batch/delete', data={'batch_id': batch['batch_id']}).get_json()['success']
    assert client.post('/api/dataset/delete', data={'dataset_id': ds['dataset_id']}).get_json()['success']
    assert client.get('/api/datasets').get_json()['datasets'] == []


def test_users_cannot_touch_each_others_data(app):
    alice, bob = app.test_client(), app.test_client()
    register_and_login(alice, 'alice')
    register_and_login(bob, 'bob')
    ds = alice.post('/api/dataset/new', data={'dataset_name': 'private'}).get_json()['dataset']

    assert bob.post('/api/dataset/delete', data={'dataset_id': ds['dataset_id']}).status_code == 404
    assert bob.get(f"/api/batches?dataset_id={ds['dataset_id']}").status_code == 404


def test_upload_rejects_non_fcs(client):
    register_and_login(client)
    ds = client.post('/api/dataset/new', data={'dataset_name': 'DS'}).get_json()['dataset']
    batch = client.post('/api/batch/new', data={'dataset_id': ds['dataset_id']}).get_json()['batch']
    res = client.post('/upload', data={'dataset': ds['dataset_id'], 'batch': batch['batch_id'],
                                       'file': (io.BytesIO(b'x'), 'evil.html')},
                      content_type='multipart/form-data')
    assert res.status_code == 400


def test_admin_routes(app, client):
    register_and_login(client, 'alice')
    assert client.get('/api/admin/users').status_code == 403

    with app.app_context():
        db.session.execute(db.update(User).where(User.username == 'alice').values(is_admin=True))
        db.session.commit()
    users = client.get('/api/admin/users').get_json()['users']
    assert [u['username'] for u in users] == ['alice']
    me = users[0]['user_id']
    assert client.post('/api/admin/delete_user', data={'user_id': me}).status_code == 400


def test_count_in_polygon():
    x = np.array([5, 10, 15, 25])
    y = np.array([5, 10, 15, 25])
    square = gate_vertices([{'x': 0, 'y': 0}, {'x': 20, 'y': 0}, {'x': 20, 'y': 20}, {'x': 0, 'y': 20}])
    assert count_in_polygon(x, y, square) == 3


def test_fluorescence_gate_scales_agree():
    from flowplatform.analysis import gate_polygon
    gate = {'ch_X': 'CD8 BUV 395', 'ch_Y': 'FSC-A',
            'coords': [{'x': 131072, 'y': 1000}, {'x': 157286, 'y': 50000}]}
    logicle = gate_polygon(gate, 'logicle', 'linear')
    assert logicle[:, 0] == pytest.approx([0.5, 0.6], abs=1e-4)
    linear = gate_polygon(gate, 'linear', 'linear')
    assert gate_polygon({**gate, 'ch_X': 'FSC-A', 'coords': [{'x': v, 'y': 0} for v in linear[:, 0]]},
                        'logicle', 'linear')[:, 0] == pytest.approx([0.5, 0.6], abs=1e-4)
