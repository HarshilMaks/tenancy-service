from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from infrastructure.config import get_settings

security = HTTPBearer(auto_error=False)


async def verify_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    settings = get_settings()

    if not settings.service.debug:
        if credentials is None:
            raise HTTPException(status_code=401, detail="Missing authorization header")
        token = credentials.credentials
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
            request.state.user_id = payload.get("sub", "anonymous")
            request.state.tenant_id = payload.get("tenant_id")
            return payload.get("sub", "anonymous")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        request.state.user_id = "dev-user"
        request.state.tenant_id = None
        return "dev-user"
