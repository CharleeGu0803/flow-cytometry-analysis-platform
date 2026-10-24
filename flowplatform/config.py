import json
import os
import secrets

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PACKAGE_DIR)


class Config:
    # Everything that is not code (database, uploads, generated plots) lives here.
    DATA_DIR = os.environ.get('FLOW_DATA_DIR', os.path.join(PROJECT_DIR, 'data'))

    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 'sqlite:///' + os.path.join(DATA_DIR, 'app.db'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Channel/gate definitions for the antibody panel.
    PANEL_CONFIG = os.environ.get('FLOW_PANEL_CONFIG', os.path.join(PACKAGE_DIR, 'default_config.json'))

    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200 MB per upload


def load_panel_config(path):
    with open(path, 'r') as f:
        return json.load(f)
