from music.auth import hashing
from music.db import core

ROLE_LISTENER = 'listener'
ROLE_ARTIST = 'artist'
ROLE_ADMIN = 'admin'
ROLES = (ROLE_LISTENER, ROLE_ARTIST, ROLE_ADMIN)

USER_COLUMNS = """
    id, username, email, first_name, last_name,
    account_type, subscription_type, is_active, is_staff, is_superuser
"""


class AuthUser:

    is_authenticated = True

    def __init__(self, row):
        self.id = row.id
        self.pk = row.id
        self.username = row.username
        self.email = row.email
        self.first_name = row.first_name
        self.last_name = row.last_name
        self.account_type = row.account_type
        self.subscription_type = row.subscription_type
        self.is_active = row.is_active
        self.is_staff = row.is_staff
        self.is_superuser = row.is_superuser

    @property
    def role(self):
        if self.is_superuser or self.is_staff:
            return ROLE_ADMIN
        return self.account_type

    def has_role(self, *roles):
        return self.role in roles

    def __str__(self):
        return self.username


class AnonymousUser:

    is_authenticated = False
    id = None
    pk = None
    username = ''
    role = None
    account_type = ''
    is_active = False
    is_staff = False
    is_superuser = False

    def has_role(self, *roles):
        return False

    def __bool__(self):
        return False

    def __str__(self):
        return 'Anonymous'


def get_by_id(user_id):
    return core.query_one(
        f'SELECT {USER_COLUMNS} FROM music_user WHERE id = %s AND is_active = TRUE',
        [user_id],
    )


def get_any_by_id(user_id):
    return core.query_one(
        f'SELECT {USER_COLUMNS} FROM music_user WHERE id = %s', [user_id]
    )


def get_by_username(username):
    return core.query_one(
        f'SELECT {USER_COLUMNS} FROM music_user WHERE LOWER(username) = LOWER(%s)',
        [username],
    )


def username_exists(username):
    return bool(core.scalar(
        'SELECT 1 FROM music_user WHERE LOWER(username) = LOWER(%s) LIMIT 1',
        [username],
    ))


def email_exists(email):
    if not email:
        return False
    return bool(core.scalar(
        "SELECT 1 FROM music_user WHERE email <> '' AND LOWER(email) = LOWER(%s) LIMIT 1",
        [email],
    ))


def create_user(username, raw_password, email='', account_type=ROLE_LISTENER,
                first_name='', last_name=''):
    if account_type not in (ROLE_LISTENER, ROLE_ARTIST):
        account_type = ROLE_LISTENER

    user_id = core.insert_returning_id(
        """
        INSERT INTO music_user (
            password, is_superuser, username, first_name, last_name, email,
            is_staff, is_active, date_joined, account_type, subscription_type,
            created_at
        )
        VALUES (%s, FALSE, %s, %s, %s, %s, FALSE, TRUE, NOW(), %s, 'free', NOW())
        RETURNING id
        """,
        [
            hashing.hash_password(raw_password),
            username, first_name, last_name, email, account_type,
        ],
    )

    user = get_by_id(user_id)
    if user is None:
        raise RuntimeError(
            f'user {username!r} was inserted as id {user_id} but could not be read back'
        )
    return user


def authenticate(username, raw_password):
    record = core.query_one(
        'SELECT id, password, is_active FROM music_user WHERE LOWER(username) = LOWER(%s)',
        [username],
    )
    if not record or not record.is_active:
        return None

    valid, needs_upgrade = hashing.verify(raw_password, record.password)
    if not valid:
        return None

    if needs_upgrade:
        set_password(record.id, raw_password)

    return get_by_id(record.id)


def set_password(user_id, raw_password):
    return core.execute(
        'UPDATE music_user SET password = %s WHERE id = %s',
        [hashing.hash_password(raw_password), user_id],
    )


def touch_last_login(user_id):
    core.execute('UPDATE music_user SET last_login = NOW() WHERE id = %s', [user_id])


def list_users(limit=200):
    return core.query(
        f"""
        SELECT {USER_COLUMNS}, date_joined, last_login,
               (SELECT COUNT(*) FROM music_playlist p WHERE p.user_id = music_user.id)
                   AS playlist_count,
               (SELECT COUNT(*) FROM music_likedtrack l WHERE l.user_id = music_user.id)
                   AS liked_count
        FROM music_user
        ORDER BY is_superuser DESC, is_staff DESC, username ASC
        LIMIT %s
        """,
        [limit],
    )


def role_counts():
    return core.query(
        """
        SELECT CASE WHEN is_superuser OR is_staff THEN 'admin'
                    ELSE account_type END AS role,
               COUNT(*) AS count
        FROM music_user
        GROUP BY 1
        ORDER BY 2 DESC
        """
    )


def promote_to_admin(user_id):
    return core.execute(
        'UPDATE music_user SET is_staff = TRUE, is_superuser = TRUE WHERE id = %s',
        [user_id],
    )


def set_account_type(user_id, account_type):
    if account_type not in (ROLE_LISTENER, ROLE_ARTIST):
        raise ValueError(f'unknown account type: {account_type}')
    return core.execute(
        """
        UPDATE music_user
        SET account_type = %s, is_staff = FALSE, is_superuser = FALSE
        WHERE id = %s
        """,
        [account_type, user_id],
    )


def set_active(user_id, is_active):
    return core.execute(
        'UPDATE music_user SET is_active = %s WHERE id = %s', [bool(is_active), user_id]
    )


def admin_count():
    return core.scalar(
        'SELECT COUNT(*) FROM music_user WHERE is_staff OR is_superuser'
    ) or 0
