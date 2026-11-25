from ninja.security import HttpBearer, SessionAuth

# Default auth for every Ninja route: a logged-in Django session.
#
# Ninja's CSRF check is off because the SvelteKit server calls Django on the
# browser's behalf and forwards only the sessionid cookie, never a CSRF token.
# Cross-site request forgery is still blocked by SESSION_COOKIE_SAMESITE = 'Lax'
# (on both Django's cookie and the copy SvelteKit sets): browsers do not attach
# the cookie to cross-site POSTs, so a forged request arrives unauthenticated.
session_auth = SessionAuth(csrf=False)


class ApiTokenAuth(HttpBearer):
    """A read-only `Authorization: Bearer <token>` (emails.ApiToken).

    Never part of the API-wide default. A route accepts a token only by listing
    this next to session_auth, and only read-only GET routes may do so;
    prospect/tests.py pins the exact set.
    """

    def authenticate(self, request, token):
        # Imported here: this module is loaded while the URLconf is being built.
        from emails.services.api_tokens import find_token

        return find_token(token)


api_token_auth = ApiTokenAuth()
