from datetime import datetime, timedelta
from api.config import Config
import bcrypt
import jwt
import uuid
import logging

def hash_password(password: str) -> str:
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)

def create_access_token(user_data: dict, expiry: timedelta = None, refresh: bool = False) -> str:
    # Calculate expiry time
    if expiry is not None:
        exp_time = datetime.now() + expiry
    else:
        exp_time = datetime.now() + timedelta(seconds=Config.JWT_ACCESS_EXPIRY)
    
    payload = {
        'user': user_data,
        'exp': int(exp_time.timestamp()),  # Convert to Unix timestamp (int)
        'jti': str(uuid.uuid4()),
        'refresh': refresh
    }
    token = jwt.encode(
        payload,
        key=Config.JWT_SECRET,
        algorithm=Config.JWT_ALGORITHM
    )
    return token

def decode_token(token: str) -> dict:
    if not token:
        logging.error("Token is empty or None")
        return None
    
    # Strip whitespace and check if it looks like a JWT (has 3 parts separated by dots)
    token = token.strip()
    if not token or token.count('.') != 2:
        logging.error(f"Invalid token format. Token parts: {token.count('.')}")
        return None
    
    try:
        token_data = jwt.decode(
            token,
            key=Config.JWT_SECRET,
            algorithms=[Config.JWT_ALGORITHM]
        )
        return token_data
    except jwt.ExpiredSignatureError:
        logging.warning("Token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logging.error(f"Invalid token: {e}")
        return None
    except Exception as e:
        logging.exception(f"Unexpected error decoding token: {e}")
        return None