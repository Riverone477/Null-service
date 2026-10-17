import os
from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Settings:
    private_key: str | None = os.getenv("PRIVATE_KEY")
    server_private_key: str | None = os.getenv("SERVER_PRIVATE_KEY")
    server_public_key: str | None = os.getenv("SERVER_PUBLIC_KEY")
    jwe_secret: str | None = os.getenv("JWE_SECRET")
    jwe_exp_minutes: int = int(os.getenv("JWE_EXP_MINUTES", "1440"))
    invitation_jws_key: str | None = os.getenv("INVITATION_JWS_KEY")
    salt: str = os.getenv("SALT", "")
    server_id: str = os.getenv("SERVER_ID", "local")

    # Login admission control (bcrypt/scrypt). All values come from env so the
    # queue size and KDF concurrency can be tuned per deployment.
    bcrypt_max_concurrency: int = _env_int("BCRYPT_MAX_CONCURRENCY", 4)
    login_queue_max_size: int = _env_int("LOGIN_QUEUE_MAX_SIZE", 500)
    login_ticket_ttl_seconds: int = _env_int("LOGIN_TICKET_TTL_SECONDS", 300)
    login_permit_ttl_seconds: int = _env_int("LOGIN_PERMIT_TTL_SECONDS", 30)
    login_outstanding_tickets_per_source: int = _env_int("LOGIN_OUTSTANDING_TICKETS_PER_SOURCE", 10)
    login_tickets_per_source_window: int = _env_int("LOGIN_TICKETS_PER_SOURCE_WINDOW", 20)
    login_tickets_per_source_ttl: int = _env_int("LOGIN_TICKETS_PER_SOURCE_TTL", 60)
    login_active_key_ttl: int = _env_int("LOGIN_ACTIVE_KEY_TTL", 3600)

    # Phone-number rate limiting.
    phone_rate_window_seconds: int = _env_int("PHONE_RATE_WINDOW_SECONDS", 600)
    phone_rate_max_in_window: int = _env_int("PHONE_RATE_MAX_IN_WINDOW", 20)


settings = Settings()



