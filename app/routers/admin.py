from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import require_admin, hash_password
from app.models.user import User
from app.models.request import Request
from app.models.history import RequestHistory
from app.schemas.request import RequestUpdate
from app.routers.requests import serialize_request
from app.services.notifications import notify
from app.services.realtime import publish
from pydantic import BaseModel, Field
from datetime import timedelta
from collections import defaultdict

router = APIRouter(prefix='/admin', tags=['admin'])


class AdminCreateIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    phone: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=4, max_length=128)
    city: str | None = None


def require_super_admin(current_admin: User = Depends(require_admin)):
    if current_admin.role != 'super_admin':
        raise HTTPException(status_code=403, detail='Primary admin access required')
    return current_admin




def _text_contains_any(text: str, keywords: list[str]) -> bool:
    text = (text or '').lower()
    return any(k in text for k in keywords)


def _local_month_key(dt):
    if not dt:
        return 'غير معروف', 'غير معروف'
    local_dt = dt + timedelta(hours=3)
    return local_dt.strftime('%Y-%m'), local_dt.strftime('%m/%Y')


@router.get('/statistics/monthly')
def monthly_statistics(db: Session = Depends(get_db), current_admin: User = Depends(require_admin)):
    safety_keywords = ['أمن', 'امان', 'أمان', 'خطر', 'خطرة', 'حريق', 'حادث', 'سرقة', 'اعتداء', 'انهيار', 'غاز', 'كهرباء مكشوف', 'سلك مكشوف']
    outage_keywords = ['انقطاع', 'مقطوع', 'كهرباء', 'مياه', 'ماء', 'انترنت', 'إنترنت', 'اتصالات', 'صرف صحي']
    resource_keywords = ['مياه', 'ماء', 'كهرباء', 'غاز', 'وقود', 'محروقات', 'خبز', 'غذاء', 'دواء', 'صيدلية', 'مشفى', 'مستشفى', 'صرف صحي', 'نظافة']
    grouped = defaultdict(lambda: {
        'month': '', 'month_label': '', 'total': 0,
        'normal': 0, 'emergency': 0, 'urgent': 0, 'dangerous': 0,
        'safety_related': 0, 'outage_related': 0, 'essential_resources': 0,
        'accepted': 0, 'rejected': 0, 'pending': 0,
    })
    requests = db.query(Request).order_by(Request.created_at.desc(), Request.id.desc()).all()
    for req in requests:
        month, label = _local_month_key(req.created_at)
        row = grouped[month]
        row['month'] = month
        row['month_label'] = label
        row['total'] += 1
        priority = (req.priority or 'normal').lower()
        if priority in {'critical', 'dangerous'}:
            row['dangerous'] += 1
        elif priority in {'high', 'urgent'}:
            row['urgent'] += 1
        elif priority == 'emergency' or req.type == 'emergency':
            row['emergency'] += 1
        else:
            row['normal'] += 1
        status = (req.status or '').lower()
        if status in {'accepted', 'resolved'}:
            row['accepted'] += 1
        elif status == 'rejected':
            row['rejected'] += 1
        else:
            row['pending'] += 1
        blob = ' '.join([req.title or '', req.category or '', req.description or '', req.type or '', req.priority or ''])
        if _text_contains_any(blob, safety_keywords) or priority in {'dangerous', 'critical'}:
            row['safety_related'] += 1
        if _text_contains_any(blob, outage_keywords):
            row['outage_related'] += 1
        if _text_contains_any(blob, resource_keywords):
            row['essential_resources'] += 1
    rows = []
    for row in grouped.values():
        total = row['total']
        critical_load = row['dangerous'] + row['urgent'] + row['emergency'] + row['safety_related'] + row['outage_related'] + row['essential_resources']
        if total >= 30 or critical_load >= 18:
            row['load_level_key'] = 'high'
            row['load_level'] = 'مرتفع'
        elif total >= 10 or critical_load >= 6:
            row['load_level_key'] = 'medium'
            row['load_level'] = 'متوسط'
        else:
            row['load_level_key'] = 'low'
            row['load_level'] = 'منخفض'
        rows.append(row)
    rows.sort(key=lambda r: r['month'], reverse=True)
    return rows[:12]

@router.get('/requests')
def admin_requests(
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    q = db.query(Request)
    if scope == 'registered':
        q = q.filter(Request.status.in_(['accepted', 'rejected']))
    elif status:
        q = q.filter(Request.status == status)
    if priority:
        q = q.filter(Request.priority == priority)

    items = q.order_by(Request.priority.desc(), Request.created_at.desc(), Request.id.desc()).all()
    return [serialize_request(r) for r in items]

@router.patch('/requests/{request_id}')
def update_request(request_id: int, payload: RequestUpdate, db: Session = Depends(get_db), current_admin: User = Depends(require_admin)):
    req = db.get(Request, request_id)
    if not req:
        raise HTTPException(status_code=404, detail='Request not found')
    old_status = req.status
    reply_text = (payload.admin_reply or '').strip()
    if payload.status:
        allowed = {'accepted', 'rejected'}
        if payload.status not in allowed:
            raise HTTPException(status_code=400, detail='Invalid status. Use accepted or rejected')
        if payload.status == 'rejected' and not reply_text:
            raise HTTPException(status_code=400, detail='عند رفض الطلب يجب كتابة سبب الرفض')
        req.status = payload.status
    if payload.priority:
        req.priority = payload.priority
    if payload.admin_reply is not None:
        req.admin_reply = payload.admin_reply.strip() or None
    req.assigned_admin_id = payload.assigned_admin_id or current_admin.id
    db.add(RequestHistory(
        request_id=req.id,
        actor_id=current_admin.id,
        action='admin_update',
        old_status=old_status,
        new_status=req.status,
        note=payload.note or payload.admin_reply,
    ))


    if req.status == 'accepted':
        notification_title = f'تم قبول الطلب #{req.id}'
        notification_message = reply_text or 'تم قبول طلبك، وصلت الرسالة وبأقرب وقت سيتم مساعدتك.'
    elif req.status == 'rejected':
        notification_title = f'تم رفض الطلب #{req.id}'
        notification_message = reply_text or 'نعتذر، تم رفض الطلب لأنه غير مناسب أو خارج نطاق المعالجة الحالية.'
    else:
        notification_title = f'تحديث على الطلب #{req.id}'
        notification_message = reply_text or 'تم تحديث طلبك.'
    if req.status != old_status or reply_text:
        notify(db, req.user_id, notification_title, notification_message)
    db.commit()
    db.refresh(req)
    publish('request_updated', serialize_request(req))
    return serialize_request(req)

@router.post('/requests/{request_id}/assign-me')
def assign_me(request_id: int, db: Session = Depends(get_db), current_admin: User = Depends(require_admin)):
    req = db.get(Request, request_id)
    if not req:
        raise HTTPException(status_code=404, detail='Request not found')
    req.assigned_admin_id = current_admin.id
    old_status = req.status
    if req.status == 'submitted':
        req.status = 'triaged'
    db.add(RequestHistory(request_id=req.id, actor_id=current_admin.id, action='assigned', old_status=old_status, new_status=req.status, note='Assigned to current admin'))
    notify(db, req.user_id, f'تم استلام الطلب #{req.id}', 'تم استلام طلبك من قبل فريق المتابعة.')
    db.commit()
    db.refresh(req)
    return serialize_request(req)


@router.post('/admins')
def create_admin(payload: AdminCreateIn, db: Session = Depends(get_db), current_admin: User = Depends(require_super_admin)):
    phone = payload.phone.strip()
    exists = db.query(User).filter(User.phone == phone).first()
    if exists:
        raise HTTPException(status_code=409, detail='هذا الحساب موجود مسبقاً')
    user = User(
        full_name=payload.full_name.strip(),
        phone=phone,
        password_hash=hash_password(payload.password),
        role='admin',
        city=(payload.city or '').strip() or None,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        'id': user.id,
        'full_name': user.full_name,
        'phone': user.phone,
        'role': user.role,
        'city': user.city,
    }
