"""CSRF tokens for the HTML form surface.

`SameSite=Lax` on the session cookie has been the only defence since 0.7.0. It
keeps the cookie off cross-site POSTs, which covers the common case, but it is
a single control enforced entirely by the browser: an older browser without
Lax-by-default, or a future deployment that loosens the cookie to
`SameSite=None` to embed the wiki somewhere, silently removes it. A token in
the session is the belt-and-braces answer, and it fails closed.

**The JSON API is deliberately not covered.** A cross-site HTML form can only
send `application/x-www-form-urlencoded`, `multipart/form-data`, or
`text/plain`, and FastAPI rejects all three on a JSON body route with a 422 —
verified, not assumed. Reaching those endpoints cross-origin needs a
preflighted `fetch`, and no CORS middleware is configured, so the browser
refuses. Requiring a token there would break every scripted API client to
close a hole that isn't open.

Tokens are issued only to signed-in users. Anonymous visitors see no form that
POSTs, so minting one for them would hand every reader a session cookie in
exchange for nothing.
"""

import secrets

from fastapi import HTTPException, Request, status

SESSION_KEY = "csrf_token"
FIELD = "csrf_token"


def issue(request: Request) -> str:
    """This session's token, minting one on first use."""
    token = request.session.get(SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_KEY] = token
    return token


def rotate(request: Request) -> None:
    """Drop the token so the next render mints a fresh one.

    Called when the session's owner changes — signing in or out — so a token
    minted before authentication can't be replayed against the session after.
    """
    request.session.pop(SESSION_KEY, None)


def is_valid(request: Request, submitted: str) -> bool:
    expected = request.session.get(SESSION_KEY)
    if not expected or not submitted:
        return False
    return secrets.compare_digest(expected, submitted)


def require(request: Request, submitted: str) -> None:
    """Reject the write unless the form carried this session's token."""
    if not is_valid(request, submitted):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this form has expired or did not come from this site — reload and try again",
        )
