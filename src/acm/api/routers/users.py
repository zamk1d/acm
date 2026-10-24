from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from acm.api.deps import UserServiceDep
from acm.api.session import start_user_session
from acm.api.templating import templates
from acm.core.exceptions import AppError

router = APIRouter(include_in_schema=False)


@router.get("/register", response_class=HTMLResponse)
async def register_form(request: Request) -> Response:
    return templates.TemplateResponse(request, "register.html", {"error": None, "email": ""})


@router.post("/register")
async def register_submit(
    request: Request,
    service: UserServiceDep,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> Response:
    try:
        user = await service.register(email, password)
    except AppError as exc:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": exc.message, "email": email},
            status_code=exc.status_code,
        )
    start_user_session(request, user.id)
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> Response:
    return templates.TemplateResponse(request, "login.html", {"error": None, "email": ""})


@router.post("/login")
async def login_submit(
    request: Request,
    service: UserServiceDep,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> Response:
    try:
        user = await service.authenticate(email, password)
    except AppError as exc:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": exc.message, "email": email},
            status_code=exc.status_code,
        )
    start_user_session(request, user.id)
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=303)