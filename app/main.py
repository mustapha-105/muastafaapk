from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.models import User, Request, RequestHistory, Notification
from app.routers import auth, requests, notifications, admin, events, ai

Base.metadata.create_all(bind=engine) 

PRIMARY_ADMIN_PHONE = 'admin'
PRIMARY_ADMIN_PASSWORD = 'admin123'
PRIMARY_ADMIN_NAME = 'المدير الأساسي'
PRIMARY_ADMIN_CITY = 'Simulation'

def ensure_primary_admin():
    from app.core.security import hash_password, verify_password
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.phone == PRIMARY_ADMIN_PHONE).first()
        if not admin:
            admin = User(
                full_name=PRIMARY_ADMIN_NAME,
                phone=PRIMARY_ADMIN_PHONE,
                password_hash=hash_password(PRIMARY_ADMIN_PASSWORD),
                role='super_admin',
                city=PRIMARY_ADMIN_CITY,
                is_active=True,
            )
            db.add(admin)
            db.commit()
        else:
            changed = False
            if admin.role != 'super_admin':
                admin.role = 'super_admin'
                changed = True
            if not verify_password(PRIMARY_ADMIN_PASSWORD, admin.password_hash):
                admin.password_hash = hash_password(PRIMARY_ADMIN_PASSWORD)
                changed = True
            if not admin.is_active:
                admin.is_active = True
                changed = True
            if changed:
                db.commit()
    finally:
        db.close()

ensure_primary_admin()

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(requests.router, prefix=settings.api_prefix)
app.include_router(notifications.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(events.router, prefix=settings.api_prefix)
app.include_router(ai.router, prefix=settings.api_prefix)

web_dir = Path(__file__).resolve().parent / 'web'
if web_dir.exists():
    app.mount('/', StaticFiles(directory=str(web_dir), html=True), name='web')

@app.get('/health')
def health():
    return {'ok': True, 'service': settings.app_name}
