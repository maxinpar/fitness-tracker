"""Cloudflare Access: Google sign-in in front of the tracker.

Access sits at Cloudflare's edge. A request for the tunnel hostname is stopped
there, sent to Google to sign in, checked against the policy, and only then
forwarded down the tunnel — carrying a signed JWT in `Cf-Access-Jwt-Assertion`
that says who it is.

THIS MODULE VERIFIES THAT JWT, and that is the whole point of it. Access at the
edge is not on its own a gate on the app: anything that can reach the origin
directly speaks to Flask without ever passing Cloudflare. Trusting the header's
presence would be worse than useless, because the header is trivially forged by
whoever is talking to the origin. So the signature is checked against
Cloudflare's published keys, the audience is checked against this one
application, and the email is checked against the allow-list.

WHY THE ORIGIN IS REACHABLE AT ALL. cloudflared connects out to Cloudflare and
forwards to http://localhost:5055, so from Flask's point of view every request —
tunnel or not — arrives from 127.0.0.1. There is therefore no way to tell "came
through Cloudflare" from "came from this machine" by address, and no loopback
exemption is possible without reopening the hole. When Access is configured,
every request needs a valid token: localhost and the phone on the home Wi-Fi
included. Reach the tracker through the hostname instead, from anywhere.

DEVELOPMENT. Leave CF_ACCESS_AUD unset and none of this runs, and the app is
open on the LAN exactly as it was before. Set it in the environment the tunnel
serves.

This is wardrobe/access.py with the demo half removed. Keep the two in step.
"""

from __future__ import annotations

import os

import jwt
from jwt import PyJWKClient

# The header Cloudflare adds. The cookie is the same token, and is what a
# browser carries on a plain navigation; both are accepted.
HEADER = "Cf-Access-Jwt-Assertion"
COOKIE = "CF_Authorization"

ALGORITHMS = ["RS256"]

# One client per team, kept because it caches Cloudflare's signing keys. Without
# this every request would fetch the JWKS over the network before rendering.
_clients: dict[str, PyJWKClient] = {}


def team_domain() -> str:
    """`yourteam.cloudflareaccess.com`, without a scheme."""
    raw = os.environ.get("CF_ACCESS_TEAM_DOMAIN", "").strip()
    return raw.replace("https://", "").replace("http://", "").rstrip("/")


def audience() -> str:
    """The Application Audience (AUD) tag of the Access application."""
    return os.environ.get("CF_ACCESS_AUD", "").strip()


def allowed_emails() -> set[str]:
    """Who may in. Comma-separated, compared lower-case."""
    raw = os.environ.get("CF_ACCESS_ALLOWED_EMAILS", "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def configured() -> bool:
    """Whether to enforce. Both halves, because one alone cannot verify."""
    return bool(team_domain() and audience())


def _client() -> PyJWKClient:
    team = team_domain()
    if team not in _clients:
        _clients[team] = PyJWKClient(
            f"https://{team}/cdn-cgi/access/certs", cache_keys=True
        )
    return _clients[team]


class Denied(Exception):
    """Why a request is not getting in. The reason is logged, never shown."""


def identity(token: str) -> str:
    """The verified email in the token, or raise Denied.

    Every check here is load-bearing:
      * the signature, against Cloudflare's published keys — this is what makes
        the header unforgeable rather than decorative
      * `aud`, against THIS application's tag — a token minted for another
        Access application in the same account (the wardrobe, say) is a valid
        Cloudflare token and must still not open the tracker
      * `iss`, against the team — a valid token from somebody else's Cloudflare
        team is likewise not a key to this door
      * expiry, which PyJWT enforces for us
    """
    if not token:
        raise Denied("no Access token on the request")
    try:
        signing_key = _client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=ALGORITHMS,
            audience=audience(),
            issuer=f"https://{team_domain()}",
        )
    except jwt.ExpiredSignatureError as exc:
        raise Denied("the Access token has expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise Denied("token is for a different Access application") from exc
    except jwt.InvalidIssuerError as exc:
        raise Denied("token is from a different Cloudflare team") from exc
    except jwt.PyJWTError as exc:
        raise Denied(f"token did not verify: {exc}") from exc
    except Exception as exc:
        # A JWKS fetch that fails must DENY, not admit. This is the one place
        # where "the network is down" and "someone is trying it on" look alike,
        # and the safe reading of both is no.
        raise Denied(f"could not check the token: {exc}") from exc

    email = str(claims.get("email") or "").strip().lower()
    if not email:
        raise Denied("token carries no email")

    allowed = allowed_emails()
    # An empty allow-list means nobody, deliberately. The Access policy is the
    # real gate and it should already be narrow; this is the second lock, and a
    # second lock that opens for everyone when misconfigured is not a lock.
    if email not in allowed:
        raise Denied(f"{email} is not on the allow-list")
    return email


def token_from(request) -> str:
    return request.headers.get(HEADER) or request.cookies.get(COOKIE) or ""
