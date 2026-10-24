from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response

from acm.api.templating import templates
from acm.core.exceptions import AppError, NotAuthenticatedError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotAuthenticatedError)
    async def _not_authenticated(request: Request, exc: NotAuthenticatedError) -> Response:
        return RedirectResponse("/", status_code=303)

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> Response:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"status_code": exc.status_code, "message": exc.message},
            status_code=exc.status_code,
        )
