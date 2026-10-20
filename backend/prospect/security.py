from ninja.security import SessionAuth

# Default auth for every Ninja route: a logged-in Django session.
#
# Ninja's CSRF check is off because the SvelteKit server calls Django on the
# browser's behalf and forwards only the sessionid cookie, never a CSRF token.
# Cross-site request forgery is still blocked by SESSION_COOKIE_SAMESITE = 'Lax'
# (on both Django's cookie and the copy SvelteKit sets): browsers do not attach
# the cookie to cross-site POSTs, so a forged request arrives unauthenticated.
session_auth = SessionAuth(csrf=False)
