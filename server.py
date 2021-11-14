import json
import os
import time
from traceback import print_exc
from typing import TypedDict, cast
import click
from flask import Flask, redirect, url_for, session
from flask.cli import with_appcontext
from flask.wrappers import Response
from flask_dance.contrib.google import make_google_blueprint
from flask_dance.consumer import oauth_authorized, oauth_before_login, oauth_error
from flask_dance.consumer.oauth2 import OAuth2ConsumerBlueprint
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin, SQLAlchemyStorage
import flask_sqlalchemy as fsql
from flask_sqlalchemy import SQLAlchemy
from flask_security import (
    UserMixin, RoleMixin, SQLAlchemyUserDatastore, Security, current_user, login_user
)
from requests import Session
from sqlalchemy.orm.exc import NoResultFound

def login(self):
    print('In overridden login method')
    self.session.redirect_uri = url_for(".authorized", _external=True)
    url, state = self.session.authorization_url(
        self.authorization_url, state=self.state, **self.authorization_url_params
    )
    state_key = f"{self.name}_oauth_state"
    session[state_key] = state
    oauth_before_login.send(self, url=url)
    return {'url': url, 'state': state}

OAuth2ConsumerBlueprint.login = login

C = fsql.sqlalchemy.Column
Int = fsql.sqlalchemy.Integer
Str = fsql.sqlalchemy.String
Bool = fsql.sqlalchemy.Boolean
DT = fsql.sqlalchemy.DateTime
FK = fsql.sqlalchemy.ForeignKey
Rel = fsql.sqlalchemy.orm.RelationshipProperty
db = SQLAlchemy()

roles_users: fsql.sqlalchemy.Table = db.Table(
    'roles_users',
    db.Column('user_id', db.Integer(), db.ForeignKey('user.id')),
    db.Column('role_id', db.Integer(), db.ForeignKey('role.id'))
)

class Role(db.Model, RoleMixin):
    id: C[Int] = db.Column(db.Integer(), primary_key=True)
    name: C[Str] = db.Column(db.String(80), unique=True)
    description: C[Str] = db.Column(db.String(255))

class User(UserMixin, db.Model):
    id: C[Int] = db.Column(db.Integer, primary_key=True)
    email: C[Str] = db.Column(db.String(255), unique=True)
    password: C[Str] = db.Column(db.String(255))
    active: C[Bool] = db.Column(db.Boolean())
    confirmed_at: C[DT] = db.Column(db.DateTime())
    roles = db.relationship(
        Role, secondary=roles_users, backref=db.backref('users', lazy='dynamic')
    )

class OAuth(OAuthConsumerMixin, db.Model):
    provider_user_id: C[Str] = db.Column(db.String(256), unique=True, nullable=False)
    user_id: C[Int] = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False)
    user: Rel = db.relationship(User)

user_datastore = SQLAlchemyUserDatastore(db, User, Role)
security = Security(datastore=user_datastore)



class GoogleWebCredentials(TypedDict):
    client_id: str
    project_id: str
    auth_uri: str
    token_uri: str
    auth_provider_x509_cert_url: str
    client_secret: str
    redirect_uris: list[str]

class GoogleCredentials(TypedDict):
    web: GoogleWebCredentials

google: Session
app = Flask(__name__)
with open('./client_secrets.json', 'rb') as f:
    creds: GoogleCredentials = json.load(f)

class Config(object):
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY') or 'asdf'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///app.sqlite3'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    GOOGLE_OAUTH_CLIENT_ID = creds['web']['client_id']
    GOOGLE_OAUTH_CLIENT_SECRET = creds['web']['client_secret']
    OAUTHLIB_RELAX_TOKEN_SCOPE = True
    OAUTHLIB_INSECURE_TRANSPORT = True
    DEBUG = True

blueprint = make_google_blueprint(
    scope=['profile', 'email', 'https://www.googleapis.com/auth/youtube.force-ssl'],
    storage=SQLAlchemyStorage(OAuth, db.session, user=current_user)
)

@click.command(name='createdb')
@with_appcontext
def create_db():
    try:
        db.create_all()
        db.session.commit()
        print("Database tables created")
    except Exception:
        print_exc()
        print("Database tables already created or something went wrong")

@oauth_authorized.connect_via(blueprint)
def google_logged_in(blueprint, token):
    if not token:
        return False

    print(token)
    resp = blueprint.session.get("/oauth2/v1/userinfo")
    if not resp.ok:
        return False

    info = resp.json()
    user_id = info["id"]

    # Find this OAuth token in the database, or create it
    query = OAuth.query.filter_by(provider=blueprint.name, provider_user_id=user_id)
    try:
        oauth = query.one()
    except NoResultFound:
        oauth = OAuth(provider=blueprint.name, provider_user_id=user_id, token=token)

    if oauth.user:
        login_user(oauth.user)

    else:
        # Create a new local user account for this user
        user = User(email=info["email"], active=True)
        # Associate the new local user account with the OAuth token
        oauth.user = user
        # Save and commit our database models
        db.session.add_all([user, oauth])
        db.session.commit()
        # Log in the new local user account
        login_user(user)

    # Disable Flask-Dance's default behavior for saving the OAuth token
    return False

app.config.from_object(Config)
app.register_blueprint(blueprint, url_prefix='/ytsp')
app.cli.add_command(create_db)
db.init_app(app)
security.init_app(app, user_datastore)

@app.route("/")
def index():
    if current_user.is_authenticated:
        token = OAuth.query.filter_by(user_id=current_user.id).one().token
        if token['expires_at'] > time.time():
            return token

    return redirect(url_for('google.login'))

app.run()