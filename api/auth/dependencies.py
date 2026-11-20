from fastapi.security import HTTPBearer
from fastapi import Request
from typing import Optional
from fastapi.security.http import HTTPAuthorizationCredentials
from .utils import decode_token
from datetime import datetime
from uuid import UUID
from api.db.redis import add_jwt_to_blacklist, is_jwt_blacklisted
from api.errors import AccessTokenRequired, InvalidId, InvalidToken, NotAuthenticated, RefreshTokenRequired, RevokedToken


def get_current_user_id(token_details: dict) -> UUID:
    user_id_str = (token_details.get("user") or {}).get("user_id")
    if not user_id_str:
        raise InvalidToken()
    try:
        return UUID(user_id_str)
    except (ValueError, TypeError):
        raise InvalidToken()


def parse_uuid(value: str, label: str) -> UUID:
    try:
        return UUID(value)
    except (ValueError, TypeError):
        raise InvalidId(f"Invalid {label} ID")

class TokenBearer(HTTPBearer):
    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)

    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials  | None]:
        credentials = await super().__call__(request)
        
        token = credentials.credentials
        
        token_data = decode_token(token)
        
        if not self.token_valid(token):
            raise InvalidToken()
        
        if await is_jwt_blacklisted(token_data.get("jti")):
            raise RevokedToken()
        
        self.verify_token_data(token_data)
        
        return token_data

    def token_valid(self, token: str) -> bool:
        token_data = decode_token(token)
        if token_data is None:
            return False
        return True
    
    def verify_token_data(self, token_data: dict) -> None:
        raise NotImplementedError("Subclasses must implement this method")
    
class AccessTokenBearer(TokenBearer):
    
    def verify_token_data(self, token_data: dict) -> None:
        if token_data and token_data.get("refresh"):
            raise AccessTokenRequired()
        if token_data.get("exp") < datetime.now().timestamp():
            raise InvalidToken()
        
async def authenticate_access_token(token: Optional[str]) -> dict:
    """Validate a raw access token (for clients like browser WebSockets that cannot send an Authorization header)."""
    if not token:
        raise NotAuthenticated()
    token_data = decode_token(token)
    if token_data is None:
        raise InvalidToken()
    if await is_jwt_blacklisted(token_data.get("jti")):
        raise RevokedToken()
    AccessTokenBearer().verify_token_data(token_data)
    return token_data


class RefreshTokenBearer(TokenBearer):
    def verify_token_data(self, token_data: dict) -> None:
        if token_data and not token_data.get("refresh"):
            raise RefreshTokenRequired()
        if token_data.get("exp") < datetime.now().timestamp():
            raise InvalidToken()
