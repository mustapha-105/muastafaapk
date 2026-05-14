from enum import Enum

class UserRole(str, Enum):
    citizen = 'citizen'
    admin = 'admin'
    dispatcher = 'dispatcher'

class RequestType(str, Enum):
    complaint = 'complaint'
    emergency = 'emergency'

class RequestStatus(str, Enum):
    submitted = 'submitted'     
    accepted = 'accepted'       
    rejected = 'rejected'      

class Priority(str, Enum):
    low = 'low'
    normal = 'normal'
    emergency = 'emergency'
    urgent = 'urgent'
    dangerous = 'dangerous'
    high = 'high'
    critical = 'critical'
