"""Opt-in Web Push for simulator commands; keys and subscriptions persist in DB."""
import base64
import json
import logging
import os
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, Integer, String, Text

from ..database import Base, get_db, SessionLocal
from ..deps import require_operator_or_admin
from ..models import User

try:
    from pywebpush import webpush, WebPushException
except ImportError:
    webpush = None
    WebPushException = Exception


class PushKey(Base):
    __tablename__ = 'test_push_key'
    id = Column(Integer, primary_key=True)
    private = Column(Text, nullable=False)
    public = Column(Text, nullable=False)


class PushSubscription(Base):
    __tablename__ = 'test_push_subscriptions'
    id = Column(Integer, primary_key=True)
    owner = Column(String(50), nullable=False)
    endpoint = Column(String(2048), unique=True, nullable=False)
    subscription = Column(Text, nullable=False)
    last_status = Column(String(50), default='registered')


class Keys(BaseModel):
    p256dh: str = Field(min_length=80, max_length=100)
    auth: str = Field(min_length=20, max_length=30)

    @field_validator('p256dh', 'auth')
    @classmethod
    def valid_key(cls, value, info):
        try:
            raw = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
            if info.field_name == 'p256dh':
                ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)
            elif len(raw) != 16:
                raise ValueError('invalid auth key')
        except Exception as error:
            raise ValueError('유효한 Web Push 키가 필요합니다.') from error
        return value


class SubscriptionInput(BaseModel):
    endpoint: str = Field(max_length=2048)
    keys: Keys

    @field_validator('endpoint')
    @classmethod
    def valid_endpoint(cls, value):
        url = urlsplit(value)
        host = url.hostname or ''
        allowed = host in ('fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com')
        allowed = allowed or host.endswith('.push.apple.com') or host.endswith('.notify.windows.com')
        if url.scheme != 'https' or not allowed or url.port not in (None, 443) or url.username or url.password:
            raise ValueError('지원되는 HTTPS 브라우저 푸시 주소가 필요합니다.')
        return value


router = APIRouter(prefix='/test-push', tags=['test-push'])


def key_pair(db):
    key = db.get(PushKey, 1)
    if key is None:
        private = ec.generate_private_key(ec.SECP256R1())
        der = private.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption())
        public = private.public_key().public_bytes(serialization.Encoding.X962,
                                                   serialization.PublicFormat.UncompressedPoint)
        key = PushKey(id=1, private=base64.urlsafe_b64encode(der).decode().rstrip('='),
                      public=base64.urlsafe_b64encode(public).decode().rstrip('='))
        db.add(key)
        try:
            db.commit()
        except Exception:
            db.rollback()
            key = db.get(PushKey, 1)
            if key is None:
                raise
    return key


@router.get('')
def config(user=Depends(require_operator_or_admin), db=Depends(get_db)):
    if webpush is None:
        return dict(available=False, reason='서버에 requirements.txt의 pywebpush 설치가 필요합니다.')
    key = key_pair(db)
    rows = db.query(PushSubscription).filter_by(owner=user.username).all()
    return dict(available=True, public_key=key.public,
                devices=[dict(id=row.id, status=row.last_status) for row in rows])


@router.post('', status_code=201)
def subscribe(body: SubscriptionInput, user=Depends(require_operator_or_admin), db=Depends(get_db)):
    if webpush is None:
        raise HTTPException(503, '서버에 pywebpush 설치가 필요합니다.')
    key_pair(db)
    row = db.query(PushSubscription).filter_by(endpoint=body.endpoint).first()
    if row is None:
        row = PushSubscription(endpoint=body.endpoint)
        db.add(row)
    row.owner = user.username
    row.subscription = json.dumps(body.model_dump())
    row.last_status = 'registered'
    db.commit()
    return dict(subscribed=True)


@router.delete('')
def unsubscribe(body: SubscriptionInput, user=Depends(require_operator_or_admin), db=Depends(get_db)):
    db.query(PushSubscription).filter_by(endpoint=body.endpoint, owner=user.username).delete()
    db.commit()
    return dict(subscribed=False)


def deliver(packet):
    if webpush is None:
        return
    with SessionLocal() as db:
        key = db.get(PushKey, 1)
        if key is None:
            return
        # Only active operators/admins remain eligible for test notifications.
        rows = db.query(PushSubscription).join(User, User.username == PushSubscription.owner).filter(
            User.active.is_(True), User.role.in_(['operator', 'admin'])).all()
        for row in rows:
            try:
                webpush(subscription_info=json.loads(row.subscription),
                        data=json.dumps(dict(title='Drown Guardian · 테스트 알림',
                                             body=packet['message'], id=packet['id']), ensure_ascii=False),
                        vapid_private_key=key.private,
                        vapid_claims={'sub': os.environ.get('DG_VAPID_SUBJECT', 'mailto:admin@example.com')},
                        ttl=60, timeout=5, headers={'Urgency': 'high'})
                row.last_status = 'accepted'
            except Exception as error:
                response = getattr(error, 'response', None)
                status = response.status_code if response is not None else None
                if status in (404, 410):
                    db.delete(row)
                else:
                    row.last_status = f'failed:{status or "network"}'
                    logging.getLogger(__name__).warning('Test push delivery failed (status=%s)', status)
        db.commit()
