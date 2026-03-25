from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError

from app.core.database import get_db
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_token_jti,
    get_token_subject,
    get_token_type,
    hash_password,
    verify_password,
)
from app.schemas import auth as schemas
from app.core.deps import get_current_user
from app.models.risk_control import RefreshToken, User

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_token_response(user: User, db):
    access_token, _ = create_access_token({"sub": user.username})
    refresh_token, refresh_expires_at, refresh_jti = create_refresh_token({"sub": user.username})
    db.add(
        RefreshToken(
            user_id=user.id,
            token_jti=refresh_jti,
            expires_at=refresh_expires_at,
        )
    )
    db.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "refresh_expires_in": REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    }


def _get_refresh_token_record(refresh_token: str, db):
    try:
        payload = decode_token(refresh_token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if get_token_type(payload) != REFRESH_TOKEN_TYPE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token type")

    username = get_token_subject(payload)
    refresh_jti = get_token_jti(payload)
    if not username or not refresh_jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed refresh token")

    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or missing user")

    token_record = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_jti == refresh_jti, RefreshToken.user_id == user.id)
        .first()
    )
    if token_record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")
    if token_record.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")
    if token_record.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    return user, token_record


@router.post('/register', response_model=schemas.UserInDB)
def register(user_in: schemas.UserCreate, db=Depends(get_db)):
    # ensure username unique
    existing = db.query(User).filter(User.username == user_in.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="username already exists")

    u = User(username=user_in.username, password_hash=hash_password(user_in.password), is_active=True, is_admin=False)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@router.post('/token', response_model=schemas.Token)
def login_for_access_token(form_data: schemas.UserCreate, db=Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    return _build_token_response(user, db)


@router.post('/refresh', response_model=schemas.Token)
def refresh_access_token(payload: schemas.RefreshTokenRequest, db=Depends(get_db)):
    user, token_record = _get_refresh_token_record(payload.refresh_token, db)
    token_record.revoked_at = datetime.utcnow()
    token_record.last_used_at = datetime.utcnow()
    db.commit()
    return _build_token_response(user, db)


@router.post('/logout', status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: schemas.RefreshTokenRequest, db=Depends(get_db)):
    user, token_record = _get_refresh_token_record(payload.refresh_token, db)
    token_record.revoked_at = datetime.utcnow()
    token_record.last_used_at = datetime.utcnow()
    db.commit()
    return None


@router.get('/me', response_model=schemas.UserInDB)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user
