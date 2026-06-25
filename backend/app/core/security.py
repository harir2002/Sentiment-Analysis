import secrets
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from app.core.config import get_settings

security = HTTPBasic()


def verify_admin(credentials: HTTPBasicCredentials = Security(security)) -> str:
    settings = get_settings()
    correct_username = secrets.compare_digest(
        credentials.username.encode(), settings.admin_username.encode()
    )
    correct_password = secrets.compare_digest(
        credentials.password.encode(), settings.admin_password.encode()
    )
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
