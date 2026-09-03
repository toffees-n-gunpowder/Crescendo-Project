import secrets
from datetime import timedelta

from django.utils import timezone

from music.db import core

COOKIE_NAME = 'crescendo_session'
SESSION_DAYS = 14
KEY_BYTES = 32


def _new_key():
    return secrets.token_hex(KEY_BYTES)


def create(user_id, user_agent='', ip_address=''):
    key = _new_key()
    expires_at = timezone.now() + timedelta(days=SESSION_DAYS)

    core.execute(
        """
        INSERT INTO app_session (session_key, user_id, created_at, expires_at,
                                 user_agent, ip_address)
        VALUES (%s, %s, NOW(), %s, %s, %s)
        """,
        [key, user_id, expires_at, (user_agent or '')[:255], (ip_address or '')[:45]],
    )
    return key


def get_user_id(session_key):
    if not session_key:
        return None

    record = core.query_one(
        """
        SELECT user_id
        FROM app_session
        WHERE session_key = %s AND expires_at > NOW()
        """,
        [session_key],
    )
    return record.user_id if record else None


def destroy(session_key):
    if not session_key:
        return 0
    return core.execute('DELETE FROM app_session WHERE session_key = %s', [session_key])


def destroy_all_for_user(user_id):
    return core.execute('DELETE FROM app_session WHERE user_id = %s', [user_id])


def purge_expired():
    return core.execute('DELETE FROM app_session WHERE expires_at <= NOW()')


def set_cookie(response, session_key):
    response.set_cookie(
        COOKIE_NAME,
        session_key,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite='Lax',
        secure=False,
    )
    return response


def clear_cookie(response):
    response.delete_cookie(COOKIE_NAME)
    return response
