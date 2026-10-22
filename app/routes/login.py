import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_model import SignIn, get_user, get_user_by_phone, save_user
from app.utils.auth import decrypt_token, issue_session, normalize_phone_number, verify_password
from app.utils.bcrypt_limit import (
    claim_permit,
    create_ticket,
    get_ticket,
    release_active,
    release_ticket,
    release_ticket_source,
)
from app.utils.db import get_db
from app.utils.jti import (
    consume_login_jti_atomic,
    get_login_jti,
    issue_login_jti,
)
from app.utils._redis import get_redis_client
from app.utils.phone_limit import PhoneRateLimiter
from app.utils.logger import LoggedAPIRouterMixin

class LoggedAPIRouter(LoggedAPIRouterMixin, APIRouter):
    pass


router = LoggedAPIRouter()


async def account_recovery(blob:str, user_id: str, password: str, db: AsyncSession):
    # delete later
    print("recovering user account")
    document = await decrypt_token(token=blob, password=password)
    # The payload is the UserAccount document. It has been serialised a few
    # different ways over time, so accept every spelling of the id and store
    # it back under the "_id" alias the rest of the app expects.
    recovered_id = (
        document.get("_id") or document.get("id") or document.get("user_id")
    )
    if recovered_id != user_id:
        print("user id mismatch")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if "_id" not in document:
        document["_id"] = recovered_id
        document.pop("id", None)

    # Handle schema version here later. Restore the user into the database
    # (the phone index lives on the row itself now).
    await save_user(db, document)

    return document


class SignInReturn(BaseModel):
    access_token: str
    refresh_token: str
    expires: int
    user_id: str
    login_jti: Optional[str] = None


@router.post("/sign-in", response_model=SignInReturn)
async def sign_in(
    user: SignIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis_client)
    ):
    # Normalize phone once, up front, for rate-limit keys + user lookup.
    user_phone: Optional[str] = None
    if user.phone_number:
        try:
            user_phone = normalize_phone_number(user.phone_number)
        except HTTPException:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Cheap source identifier for per-source queue/ticket limits.
    source_id = f"{request.client.host if request.client else 'unknown'}:{(user_phone or user.user_id or 'anon')}"

    # ------------------------------------------------------------------
    # Flow 1: Returning device presenting a valid single-use login JTI.
    # ------------------------------------------------------------------
    limiter = PhoneRateLimiter(redis)
    permit_active = False
    if user.jti:
        # Efficient lookup first, without consuming, so an invalid JTI never
        # spends bcrypt and is never burned.
        jti_record = await get_login_jti(user.jti, redis)
        if not jti_record:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        # Cheap phone-number rate limit BEFORE consuming the single-use JTI,
        # so a legitimate user never loses a JTI to a rate-limit rejection.
        if user_phone:
            cooldown, ttl = await limiter.is_cooldown(user_phone)
            if cooldown:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                    detail="Too many attempts, try again later",
                                    headers={"Retry-After": str(max(1, ttl))})
            allowed, _ = await limiter.check_and_inc(user_phone)
            if not allowed:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                    detail="Too many attempts, try again later",
                                    headers={"Retry-After": "300"})

        # Point of no return. The JTI is deleted; it is NEVER valid again --
        # no rollback, no reissue of the same id. The Lua consume is atomic,
        # so concurrent requests can never both succeed on one JTI.
        try:
            await consume_login_jti_atomic(user.jti, redis=redis)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    else:
        # ------------------------------------------------------------------
        # Flow 2: New or unrecognized device (no JTI).
        # ------------------------------------------------------------------
        if user_phone:
            cooldown, ttl = await limiter.is_cooldown(user_phone)
            if cooldown:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                    detail="Too many attempts, try again later",
                                    headers={"Retry-After": str(max(1, ttl))})
            allowed, _ = await limiter.check_and_inc(user_phone)
            if not allowed:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                    detail="Too many attempts, try again later",
                                    headers={"Retry-After": "300"})

        # Claim a permit for the FIFO head, or (queue empty) acquire capacity
        # directly. A permit is a short-lived single-use authorization to run
        # the KDF; it is claimed and immediately spent in this same request.
        claimed = False
        permit_id = None
        ticket_id = user.queue_ticket_id or ""
        if ticket_id:
            ticket = await get_ticket(ticket_id, redis)
            if not ticket or int(ticket.get("expires_at", 0)) < int(time.time()):
                await release_ticket(ticket_id, redis)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Login ticket expired, please retry",
                    headers={"Retry-After": "1"},
                )

        code, info = await claim_permit(ticket_id=ticket_id, redis=redis)
        if code == 1:
            claimed = True
            permit_id = info["permit_id"]
            if ticket_id:
                # Ticket was consumed atomically inside claim_permit; only
                # release the per-source outstanding slot here.
                await release_ticket_source(ticket.get("source"), redis)
        elif code == 2:
            # Ticket valid but not eligible yet (not head / no slot).
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Login queue busy, try again shortly",
                headers={"Retry-After": "5"},
            )
        elif code == 3:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Login ticket expired, please retry",
                headers={"Retry-After": "1"},
            )
        else:
            # At capacity: no bcrypt runs. Hand the client a bounded,
            # expiring ticket instead of a reserved slot.
            new_ticket = await create_ticket(source_id, redis)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": "Login queue busy, try again shortly",
                    "queue_ticket_id": new_ticket["tid"],
                },
                headers={"Retry-After": "5"},
            )

        if not claimed or not permit_id:
            raise HTTPException(status_code=503, detail="Login service busy, try again shortly")

        # Track active bcrypt slot so we can release it in a finally block.
        permit_active = True

    # ------------------------------------------------------------------
    # Shared: resolve user document (Flow 1 with/without JTI, Flow 2).
    # ------------------------------------------------------------------
    user_id = None
    user_doc = None
    try:
        if user.user_id:
            user_id = user.user_id
            user_doc = await get_user(db, user_id)
        elif user_phone:
            user_doc = await get_user_by_phone(db, user_phone)
            if user_doc:
                user_id = user_doc["_id"]
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not user_doc and not user.security_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if user.security_token:
            user_doc = await account_recovery(blob=user.security_token, user_id=user_id, password=user.password, db=db)

        # Password verification happens only after JTI/rate-limit/permit checks.
        if not verify_password(user.password, user_doc["salt"], user_doc["password"]):
            # Record failure for progressive cooldown (prevents victim lockout).
            if user_phone:
                await limiter.record_failure(user_phone)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        # Successful login: clear failure counters.
        if user_phone:
            await limiter.clear_failures(user_phone)

        # Issue a fresh session. A returning device (Flow 1) rotates its JTI:
        # the old one was just consumed/deleted, so we mint a new one. Flow 2
        # is an unrecognized device and gets NO JTI.
        session = await issue_session(user_id, access_expires_minutes=24*60,
                                      refresh_expires_minutes=24*60*7)

        
        new_jti = await issue_login_jti(
                redis,
                user_id=user_id,
                phone_number=user_phone or "",
            )

        return SignInReturn(
            access_token=session["access_token"],
            refresh_token=session["refresh_token"],
            expires=24*60*60,  # 24 hours in seconds,
            user_id=user_id,
            login_jti=new_jti,
        )
    finally:
        # Release bcrypt permit capacity on any outcome (success, failure, cancel, exception).
        if permit_active:
            await release_active(redis)

