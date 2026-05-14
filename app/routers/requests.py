from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.request import Request
from app.models.history import RequestHistory
from app.schemas.request import RequestCreate, RequestOut, HistoryOut
from app.services.notifications import notify
from app.services.realtime import publish

router = APIRouter(prefix='/requests', tags=['requests'])

def serialize_request(req: Request) -> dict:
    return {
        'id': req.id,
        'user_id': req.user_id,
        'assigned_admin_id': req.assigned_admin_id,
        'type': req.type,
        'title': req.title,
        'category': req.category,
        'description': req.description,
        'latitude': req.latitude,
        'longitude': req.longitude,
        'city': req.city,
        'priority': req.priority,
        'status': req.status,
        'admin_reply': req.admin_reply,
        'citizen_name': req.citizen.full_name if req.citizen else None,
        'citizen_phone': req.citizen.phone if req.citizen else None,
        'created_at': req.created_at,
        'updated_at': req.updated_at,
    }

@router.post('', response_model=RequestOut)
def create_request(payload: RequestCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Only normal citizens can create complaints/emergency reports.
    # Admin accounts are operational accounts and cannot submit citizen requests.
    if current_user.role != 'citizen':
        raise HTTPException(status_code=403, detail='Only normal users can submit complaints')
    if payload.latitude is None or payload.longitude is None:
        raise HTTPException(status_code=400, detail='Location is required')
    priority = 'critical' if payload.type == 'emergency' else payload.priority
    req = Request(
        user_id=current_user.id,
        type=payload.type,
        title=payload.title.strip(),
        category=(payload.category or '').strip() or None,
        description=payload.description.strip(),
        latitude=payload.latitude,
        longitude=payload.longitude,
        city=(payload.city or current_user.city or '').strip() or None,
        priority=priority,
        status='submitted',
    )
    db.add(req)
    db.flush()
    db.add(RequestHistory(request_id=req.id, actor_id=current_user.id, action='created', new_status='submitted', note='Citizen submitted the request'))
    admins = db.query(User).filter(User.role.in_(['admin', 'dispatcher', 'super_admin']), User.is_active == True).all()
    for admin in admins:
        notify(db, admin.id, 'طلب جديد' if payload.type == 'complaint' else 'بلاغ طارئ جديد', f'#{req.id} - {req.title}')
    db.commit()
    db.refresh(req)
    publish('request_created', serialize_request(req))
    return serialize_request(req)

@router.get('', response_model=list[RequestOut])
def my_requests(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Request)
    if current_user.role in {'admin', 'dispatcher'}:
        # For admins, "My requests" means requests assigned/claimed by the current admin.
        q = q.filter(Request.assigned_admin_id == current_user.id)
    else:
        # For citizens, "My requests" means the complaints/reports they submitted.
        q = q.filter(Request.user_id == current_user.id)
    items = q.order_by(Request.created_at.desc(), Request.id.desc()).all()
    return [serialize_request(r) for r in items]

@router.get('/{request_id}', response_model=RequestOut)
def get_request(request_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    req = db.get(Request, request_id)
    if not req:
        raise HTTPException(status_code=404, detail='Request not found')
    if current_user.role not in {'admin', 'dispatcher'} and req.user_id != current_user.id:
        raise HTTPException(status_code=403, detail='Not allowed')
    return serialize_request(req)

@router.get('/{request_id}/history', response_model=list[HistoryOut])
def request_history(request_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    req = db.get(Request, request_id)
    if not req:
        raise HTTPException(status_code=404, detail='Request not found')
    if current_user.role not in {'admin', 'dispatcher'} and req.user_id != current_user.id:
        raise HTTPException(status_code=403, detail='Not allowed')
    return db.query(RequestHistory).filter(RequestHistory.request_id == request_id).order_by(RequestHistory.created_at.asc()).all()
