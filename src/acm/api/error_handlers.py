from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from acm.api.templating import templates
from acm.core.exceptions import AppError, NotAuthenticatedError


def _wants_json(request: Request) -> bool:
    """fetch()/XHR calls get JSON errors, page navigations get HTML.

    Browsers send `Sec-Fetch-Dest: empty` for fetch/XHR and `document` for navigations.
    """
    return (
        "application/json" in request.headers.get("accept", "")
        or request.headers.get("sec-fetch-dest") == "empty"
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotAuthenticatedError)
    async def _not_authenticated(request: Request, exc: NotAuthenticatedError) -> Response:
        if _wants_json(request):
            return JSONResponse({"detail": exc.message}, status_code=exc.status_code)
        return RedirectResponse("/", status_code=303)

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> Response:
        if _wants_json(request):
            return JSONResponse({"detail": exc.message}, status_code=exc.status_code)
        return templates.TemplateResponse(
            request,
            "error.html",
            {"status_code": exc.status_code, "message": exc.message},
            status_code=exc.status_code,
        )