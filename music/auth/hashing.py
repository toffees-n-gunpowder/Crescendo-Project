import hashlib
import hmac
import secrets

SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
DIGEST_LEN = 32
SALT_BYTES = 16


def hash_password(raw_password):
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(
        raw_password.encode('utf-8'),
        salt=salt,
        n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
        dklen=DIGEST_LEN,
        maxmem=64 * 1024 * 1024,
    )
    return f'scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}'


def _verify_scrypt(raw_password, stored):
    try:
        _, n, r, p, salt_hex, digest_hex = stored.split('$')
        digest = hashlib.scrypt(
            raw_password.encode('utf-8'),
            salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p),
            dklen=len(bytes.fromhex(digest_hex)),
            maxmem=64 * 1024 * 1024,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def _verify_pbkdf2(raw_password, stored):
    import base64
    try:
        _, iterations, salt, digest_b64 = stored.split('$')
        expected = base64.b64decode(digest_b64)
        digest = hashlib.pbkdf2_hmac(
            'sha256',
            raw_password.encode('utf-8'),
            salt.encode('utf-8'),
            int(iterations),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


def verify(raw_password, stored):
    if not raw_password or not stored:
        return False, False

    if stored.startswith('scrypt$'):
        return _verify_scrypt(raw_password, stored), False

    if stored.startswith('pbkdf2_sha256$'):
        return _verify_pbkdf2(raw_password, stored), True

    return False, False
