"""FastAPI app instance — router includes, health check, global error handling."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.companies import router as companies_router

logger = logging.getLogger("app")

app = FastAPI(title="Data Center Stocks API")
app.include_router(companies_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # T-01-04: stack traces and internal paths must never reach API clients.
    logger.exception("unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
