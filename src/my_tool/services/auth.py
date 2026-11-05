"""本地试点密码与 JWT；生产应对接组织身份系统。"""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
import jwt

ITERATIONS = 310000

def hash_password(password):
    if len(password) < 12:
        raise ValueError('密码至少需要 12 个字符')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f'{ITERATIONS}${salt}${digest}'

def verify_password(password, encoded):
    try:
        iterations, salt, expected = encoded.split('$')
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

def signing_key():
    key = os.getenv('PILOT_JWT_SECRET', '')
    if len(key) < 32:
        raise RuntimeError('请配置至少 32 个字符的 PILOT_JWT_SECRET')
    return key

def issue_token(user_id, session_id):
    now = datetime.now(timezone.utc)
    return jwt.encode({'sub': str(user_id), 'jti': session_id, 'iat': now, 'exp': now + timedelta(minutes=30), 'iss': 'procurement-pilot'}, signing_key(), algorithm='HS256')

def decode_token(token):
    claims = jwt.decode(token, signing_key(), algorithms=['HS256'], issuer='procurement-pilot', options={'require':['sub','jti','iat','exp','iss']})
    return int(claims['sub']), claims['jti']
