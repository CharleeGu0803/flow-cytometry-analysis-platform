import os

import click
from flask import Flask, g
from werkzeug.security import generate_password_hash

from .auth import load_current_user
from .config import Config, load_panel_config
from .models import db, User


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config:
        app.config.update(config)

    os.makedirs(app.config['DATA_DIR'], exist_ok=True)
    app.config['PANEL'] = load_panel_config(app.config['PANEL_CONFIG'])

    db.init_app(app)
    app.before_request(load_current_user)

    @app.context_processor
    def inject_user():
        return {'current_user': g.get('user')}

    from . import admin, views

    @app.template_filter('plural')
    def plural(count, singular, plural_form=None):
        return f'{count} {singular if count == 1 else plural_form or singular + "s"}'

    app.add_template_filter(views.utc_iso, 'utc_iso')

    app.register_blueprint(views.bp)
    app.register_blueprint(admin.bp)

    with app.app_context():
        db.create_all()

    @app.cli.command('create-admin')
    @click.argument('username')
    @click.password_option()
    def create_admin(username, password):
        """Create an admin account, or promote and reset an existing user."""
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(username=username)
            db.session.add(user)
        user.password = generate_password_hash(password)
        user.is_admin = True
        db.session.commit()
        click.echo(f'Admin user "{username}" is ready.')

    return app
