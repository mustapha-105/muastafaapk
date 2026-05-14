from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix='/ai', tags=['ai'])


class AnalyzeIn(BaseModel):
    title: str | None = None
    description: str
    category: str | None = None
    type: str = 'complaint'
    priority: str | None = None
    governorate: str | None = None
    area: str | None = None


class AnalyzeOut(BaseModel):
    priority: str
    priority_label: str
    category: str
    summary: str
    reason: str
    suggested_reply: str
    risk_score: int
    urgency_score: int
    service_score: int
    location_score: int
    confidence_score: int
    confidence_label: str
    keywords: list[str]
    fuzzy_factors: dict[str, int]
    advice: str


PRIORITY_LABELS = {
    'normal': 'عادية',
    'emergency': 'طارئة',
    'urgent': 'مستعجلة',
    'dangerous': 'خطرة',
}

CATEGORY_KEYWORDS = [
    ('السلامة العامة / الكهرباء', ['كهرباء', 'كبل', 'كابل', 'سلك', 'أسلاك', 'ماس', 'صعق', 'عامود', 'عمود', 'مكشوف', 'محولة', 'توتر']),
    ('السلامة العامة / الحريق والغاز', ['حريق', 'دخان', 'غاز', 'تسريب غاز', 'انفجار', 'رائحة غاز', 'اشتعال', 'لهب']),
    ('المياه والصرف الصحي', ['مياه', 'ماء', 'تسريب', 'صرف', 'مجاري', 'فيضان', 'انسداد', 'مجرور', 'مجارير']),
    ('النظافة والبيئة', ['قمامة', 'زبالة', 'نفايات', 'نظافة', 'روائح', 'حاوية', 'كلاب', 'حشرات', 'تلوث']),
    ('الطرقات والإنارة', ['طريق', 'شارع', 'حفرة', 'زفت', 'رصيف', 'إنارة', 'انارة', 'مطب', 'إشارة', 'اشارة', 'جسر']),
    ('الأمن والسلامة', ['سرقة', 'اعتداء', 'مشاجرة', 'تهديد', 'سلاح', 'خطر', 'أطفال', 'اطفال', 'انهيار', 'تجمع']),
    ('الموارد الأساسية', ['خبز', 'دواء', 'صيدلية', 'مشفى', 'مستشفى', 'محروقات', 'وقود', 'كازية', 'غذاء']),
]

DANGEROUS_KEYWORDS = ['خطر', 'خطير', 'خطرة', 'حريق', 'غاز', 'انفجار', 'صعق', 'كهرباء مكشوف', 'سلك مكشوف', 'كبل مكشوف', 'انهيار', 'أطفال', 'اطفال', 'مصاب', 'إصابة', 'اصابة', 'نزيف', 'حادث', 'دخان', 'موت', 'اختناق']
URGENT_KEYWORDS = ['مستعجل', 'عاجل', 'فوري', 'مغلق', 'انسداد', 'فيضان', 'تسريب', 'مقطوع', 'انقطاع', 'تعطل', 'حفرة كبيرة', 'ازدحام', 'توقف']
EMERGENCY_KEYWORDS = ['طارئ', 'طوارئ', 'حادث', 'حريق', 'غاز', 'إسعاف', 'اسعاف', 'شرطة', 'خطر مباشر', 'انقاذ', 'إخلاء', 'اخلاء']
SERVICE_KEYWORDS = ['مياه', 'ماء', 'كهرباء', 'غاز', 'صرف صحي', 'مشفى', 'مستشفى', 'دواء', 'خبز', 'وقود', 'محروقات', 'إنارة', 'انارة', 'اتصالات', 'انترنت', 'إنترنت']


HIGH_DENSITY_GOVERNORATES = ['دمشق', 'حلب', 'حمص', 'حماة', 'اللاذقية', 'طرطوس']
SENSITIVE_AREA_KEYWORDS = ['مدرسة', 'جامعة', 'مشفى', 'مستشفى', 'سوق', 'شارع رئيسي', 'طريق رئيسي', 'كراج', 'محطة', 'فرن', 'جامع', 'كنيسة', 'حديقة', 'روضة']
INDUSTRIAL_AREA_KEYWORDS = ['صناعية', 'معمل', 'مصنع', 'ورشة', 'مستودع', 'كازية', 'محروقات']
RESIDENTIAL_AREA_KEYWORDS = ['سكني', 'حي', 'بناء', 'أطفال', 'اطفال', 'مدخل', 'حارة']


def _norm(text: str) -> str:
    return (text or '').strip().lower()


def _hits(text: str, words: list[str]) -> list[str]:
    return [w for w in words if w.lower() in text]


def _clamp(value: float, low: int = 0, high: int = 100) -> int:
    return int(max(low, min(high, round(value))))


def _unique(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


def _short_summary(title: str, description: str, category: str, priority_label: str) -> str:
    source = description.strip() or title.strip()
    if len(source) > 150:
        source = source[:147].rstrip() + '...'
    cat_part = f' ضمن {category}' if category else ''
    return f'بلاغ {priority_label}{cat_part}: {source}'


def _category_for_text(text: str, category_input: str) -> tuple[str, list[str]]:
    if category_input:
        return category_input, []
    for category, words in CATEGORY_KEYWORDS:
        hits = _hits(text, words)
        if hits:
            return category, hits[:4]
    return 'خدمات عامة', []


def _location_score(governorate: str, area: str, text: str) -> tuple[int, list[str]]:
    loc_text = _norm(' '.join([governorate, area, text]))
    score = 0
    reasons: list[str] = []

    if any(g.lower() in loc_text for g in HIGH_DENSITY_GOVERNORATES):
        score += 10
        reasons.append('محافظة/مدينة ذات كثافة عالية')

    sensitive_hits = _hits(loc_text, SENSITIVE_AREA_KEYWORDS)
    industrial_hits = _hits(loc_text, INDUSTRIAL_AREA_KEYWORDS)
    residential_hits = _hits(loc_text, RESIDENTIAL_AREA_KEYWORDS)

    if sensitive_hits:
        score += 28
        reasons.extend(sensitive_hits[:3])
    if industrial_hits:
        score += 22
        reasons.extend(industrial_hits[:3])
    if residential_hits:
        score += 14
        reasons.extend(residential_hits[:3])

    return _clamp(score), _unique(reasons)


def _confidence_label(score: int) -> str:
    if score >= 75:
        return 'عالية'
    if score >= 50:
        return 'متوسطة'
    return 'منخفضة'


@router.post('/analyze', response_model=AnalyzeOut)
def analyze(payload: AnalyzeIn, current_user: User = Depends(get_current_user)):
    title = (payload.title or '').strip()
    description = (payload.description or '').strip()
    category_input = (payload.category or '').strip()
    governorate = (payload.governorate or current_user.city or '').strip()
    area = (payload.area or '').strip()
    selected_priority = (payload.priority or '').strip().lower()
    request_type = (payload.type or 'complaint').strip().lower()

    text = _norm(' '.join([title, description, category_input, governorate, area, request_type, selected_priority]))
    found_category, category_hits = _category_for_text(text, category_input)

    dangerous_hits = _hits(text, DANGEROUS_KEYWORDS)
    urgent_hits = _hits(text, URGENT_KEYWORDS)
    emergency_hits = _hits(text, EMERGENCY_KEYWORDS)
    service_hits = _hits(text, SERVICE_KEYWORDS)
    location_score, location_hits = _location_score(governorate, area, text)


    danger_membership = _clamp(18 + len(dangerous_hits) * 17 + len(emergency_hits) * 10)
    urgency_membership = _clamp(14 + len(urgent_hits) * 15 + len(emergency_hits) * 13)
    service_membership = _clamp(len(service_hits) * 16)

    if request_type == 'emergency':
        danger_membership = max(danger_membership, 62)
        urgency_membership = max(urgency_membership, 70)
    if selected_priority in {'dangerous', 'critical'}:
        danger_membership = max(danger_membership, 76)
    elif selected_priority in {'emergency'}:
        danger_membership = max(danger_membership, 62)
        urgency_membership = max(urgency_membership, 66)
    elif selected_priority in {'urgent', 'high'}:
        urgency_membership = max(urgency_membership, 58)


    risk_score = _clamp(
        danger_membership * 0.44
        + urgency_membership * 0.25
        + location_score * 0.18
        + service_membership * 0.13
    )

    if risk_score >= 82:
        priority = 'dangerous'
    elif risk_score >= 64:
        priority = 'emergency'
    elif risk_score >= 42:
        priority = 'urgent'
    else:
        priority = 'normal'

    confidence_score = _clamp(35 + len(_unique(category_hits + dangerous_hits + urgent_hits + emergency_hits + service_hits + location_hits)) * 7)
    if description and len(description) >= 25:
        confidence_score = _clamp(confidence_score + 12)
    if governorate or area:
        confidence_score = _clamp(confidence_score + 8)

    all_hits = _unique(category_hits + dangerous_hits + urgent_hits + emergency_hits + service_hits + location_hits)
    priority_label = PRIORITY_LABELS.get(priority, priority)
    summary = _short_summary(title, description, found_category, priority_label)

    factor_parts = [
        f'خطورة النص {danger_membership}%',
        f'الاستعجال {urgency_membership}%',
        f'تأثير الموقع {location_score}%',
        f'الخدمات الأساسية {service_membership}%',
    ]
    if all_hits:
        reason = '' + '، '.join(factor_parts) + '. الكلمات/العوامل المؤثرة: ' + '، '.join(all_hits[:8]) + '.'
    else:
        reason = 'لم تظهر مؤشرات خطورة قوية؛ لذلك بقي التصنيف ضمن المستوى العادي أو القابل للمراجعة.'

    place_text = ''
    if governorate or area:
        place_text = f' في {governorate}{" - " if governorate and area else ""}{area}'

    if priority == 'dangerous':
        suggested_reply = f'تم استلام بلاغك، وبحسب التحليل الذكي توجد مؤشرات خطورة عالية وسيتم التعامل معه بأولوية قصوى وإحالته للجهة المختصة.'
        advice = 'ابتعد عن مكان الخطر، ولا تحاول المعالجة الشخصية، واذكر أقرب نقطة واضحة إذا أمكن.'
    elif priority == 'emergency':
        suggested_reply = f'تم استلام البلاغ الطارئ، وسيتم مراجعته بسرعة وتحويله للجهة المختصة.'
        advice = 'إذا كان هناك خطر مباشر على الحياة يرجى التواصل أيضًا مع رقم الطوارئ المحلي فورًا.'
    elif priority == 'urgent':
        suggested_reply = f'تم استلام طلبك، وسيتم التعامل معه كحالة مستعجلة حسب توفر الفريق المختص.'
        advice = 'أضف تفاصيل أوضح عن المنطقة أو أقرب معلم لتسريع الوصول.'
    else:
        suggested_reply = f'تم استلام طلبك، وسيتم مراجعته من قبل الإدارة والرد عليك بأقرب وقت.'
        advice = 'الوصف واضح مبدئيًا، ويمكن إضافة تفاصيل عن المنطقة أو صورة لاحقًا إذا توفرت.'

    return AnalyzeOut(
        priority=priority,
        priority_label=priority_label,
        category=found_category,
        summary=summary,
        reason=reason,
        suggested_reply=suggested_reply,
        risk_score=risk_score,
        urgency_score=urgency_membership,
        service_score=service_membership,
        location_score=location_score,
        confidence_score=confidence_score,
        confidence_label=_confidence_label(confidence_score),
        keywords=all_hits[:10],
        fuzzy_factors={
            'text_risk': danger_membership,
            'urgency': urgency_membership,
            'location': location_score,
            'essential_services': service_membership,
            'final_risk': risk_score,
            'confidence': confidence_score,
        },
        advice=advice,
    )
