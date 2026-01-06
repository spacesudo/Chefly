from fastapi.security import HTTPBearer
from fastapi import Request
from typing import Optional
from fastapi.security.http import HTTPAuthorizationCredentials
from .utils import decode_token
from fastapi import HTTPException, status
from datetime import datetime
from api.db.redis import add_jwt_to_blacklist, is_jwt_blacklisted

class TokenBearer(HTTPBearer):
    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)

    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials  | None]:
        credentials = await super().__call__(request)
        
        token = credentials.credentials
        
        token_data = decode_token(token)
        
        if not self.token_valid(token):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token or expired")
        
        if await is_jwt_blacklisted(token_data.get("jti")):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token is Expired or Revoked")
        
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
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Refresh token used")
        if token_data.get("exp") < datetime.now().timestamp():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token expired")
        
class RefreshTokenBearer(TokenBearer):
    def verify_token_data(self, token_data: dict) -> None:
        if token_data and not token_data.get("refresh"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access token used")
        if token_data.get("exp") < datetime.now().timestamp():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token expired")