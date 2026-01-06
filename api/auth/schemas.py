from pydantic import BaseModel, EmailStr, Field, field_validator
import re

class UserCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=100, examples=["Password123!"], exclude=True)
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"
        if not re.match(pattern, v):
            raise ValueError(
                "Password must be at least 8 characters long and contain: "
                "at least one lowercase letter, one uppercase letter, one digit, "
                "and one special character (@$!%*?&)"
            )
        return v
    
class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)
    

    