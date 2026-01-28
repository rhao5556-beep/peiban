def validate_production_settings(settings) -> None:
    if getattr(settings, "DEBUG", False):
        return

    insecure_jwt_secrets = {
        "your-secret-key-change-in-production",
        "your-secret-key",
        "your-super-secret-key-change-in-production",
    }
    jwt_secret = getattr(settings, "JWT_SECRET", "") or ""
    if (not jwt_secret) or (jwt_secret in insecure_jwt_secrets) or (len(jwt_secret) < 32):
        raise RuntimeError("JWT_SECRET must be set to a strong value in production")

    token_issue_secret = getattr(settings, "TOKEN_ISSUE_SECRET", "") or ""
    allow_local = bool(getattr(settings, "ALLOW_LOCAL_TOKEN_ISSUE", False))
    if not allow_local:
        if not token_issue_secret or len(token_issue_secret) < 16:
            raise RuntimeError("TOKEN_ISSUE_SECRET must be set in production")

        auth_session_secret = getattr(settings, "AUTH_SESSION_SECRET", "") or ""
        if not auth_session_secret or len(auth_session_secret) < 32:
            raise RuntimeError("AUTH_SESSION_SECRET must be set to a strong value in production")

    if getattr(settings, "AUTH_ALLOW_CLIENT_USER_ID", False):
        raise RuntimeError("AUTH_ALLOW_CLIENT_USER_ID must be disabled in production")
