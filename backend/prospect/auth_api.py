from django.contrib.auth import authenticate, login, logout
from ninja import Router, Schema

router = Router()


class LoginRequest(Schema):
    username: str
    password: str


class UserOut(Schema):
    username: str
    email: str


@router.post("/login", response={200: UserOut, 401: dict}, auth=None)
def auth_login(request, payload: LoginRequest):
    user = authenticate(request, username=payload.username, password=payload.password)
    if user is None:
        return 401, {"detail": "Invalid credentials"}
    login(request, user)
    return 200, UserOut(username=user.username, email=user.email)


@router.post("/logout", response={200: dict}, auth=None)
def auth_logout(request):
    logout(request)
    return {"detail": "Logged out"}


@router.get("/me", response={200: UserOut, 401: dict})
def auth_me(request):
    if not request.user.is_authenticated:
        return 401, {"detail": "Not authenticated"}
    return 200, UserOut(username=request.user.username, email=request.user.email)
