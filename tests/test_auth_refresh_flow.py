from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import auth as auth_api
from app.core import deps as deps_module
from app.core.database import get_db as core_get_db
from app.core.security import hash_password
from app.models.base import Base
from app.models.risk_control import User


def _create_test_client():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(auth_api.router, prefix='/api/v1')
    app.dependency_overrides[core_get_db] = override_get_db
    app.dependency_overrides[deps_module.get_db] = override_get_db

    return TestClient(app), testing_session_local, engine, app


def _seed_user(session_factory, username='tester', password='secret123'):
    session = session_factory()
    user = User(
        username=username,
        password_hash=hash_password(password),
        is_active=True,
        is_admin=False,
    )
    session.add(user)
    session.commit()
    session.close()
    return {'username': username, 'password': password}


def _login(client, credentials):
    response = client.post('/api/v1/auth/token', json=credentials)
    assert response.status_code == 200
    return response.json()


def test_login_returns_access_and_refresh_tokens():
    client, session_factory, engine, app = _create_test_client()
    try:
        credentials = _seed_user(session_factory)

        payload = _login(client, credentials)

        assert payload['token_type'] == 'bearer'
        assert payload['access_token']
        assert payload['refresh_token']
        assert payload['expires_in'] > 0
        assert payload['refresh_expires_in'] > 0

        me_response = client.get(
            '/api/v1/auth/me',
            headers={'Authorization': f"Bearer {payload['access_token']}"},
        )
        assert me_response.status_code == 200
        assert me_response.json()['username'] == credentials['username']
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_refresh_rotates_refresh_token_and_revokes_previous_one():
    client, session_factory, engine, app = _create_test_client()
    try:
        credentials = _seed_user(session_factory)
        login_payload = _login(client, credentials)

        refresh_response = client.post(
            '/api/v1/auth/refresh',
            json={'refresh_token': login_payload['refresh_token']},
        )
        assert refresh_response.status_code == 200
        refreshed_payload = refresh_response.json()
        assert refreshed_payload['refresh_token'] != login_payload['refresh_token']

        revoked_response = client.post(
            '/api/v1/auth/refresh',
            json={'refresh_token': login_payload['refresh_token']},
        )
        assert revoked_response.status_code == 401

        current_response = client.post(
            '/api/v1/auth/refresh',
            json={'refresh_token': refreshed_payload['refresh_token']},
        )
        assert current_response.status_code == 200
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_refresh_token_cannot_be_used_for_me_endpoint():
    client, session_factory, engine, app = _create_test_client()
    try:
        credentials = _seed_user(session_factory)
        payload = _login(client, credentials)

        me_response = client.get(
            '/api/v1/auth/me',
            headers={'Authorization': f"Bearer {payload['refresh_token']}"},
        )
        assert me_response.status_code == 401
        assert me_response.json()['detail'] == 'Invalid token type'
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_logout_revokes_refresh_token():
    client, session_factory, engine, app = _create_test_client()
    try:
        credentials = _seed_user(session_factory)
        payload = _login(client, credentials)

        logout_response = client.post(
            '/api/v1/auth/logout',
            json={'refresh_token': payload['refresh_token']},
        )
        assert logout_response.status_code == 204

        refresh_response = client.post(
            '/api/v1/auth/refresh',
            json={'refresh_token': payload['refresh_token']},
        )
        assert refresh_response.status_code == 401
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()