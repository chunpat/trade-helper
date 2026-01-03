from fastapi import APIRouter, Depends, HTTPException, status
from datetime import timedelta

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.schemas import auth as schemas
from app.core.deps import get_current_user
from app.models.risk_control import User

router = APIRouter(prefix="/auth", tags=["auth"])


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

    access_token_expires = timedelta(minutes=30)
    token = create_access_token({"sub": user.username}, expires_delta=access_token_expires)

    return {"access_token": token, "token_type": "bearer"}


@router.get('/me', response_model=schemas.UserInDB)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user
