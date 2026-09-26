from fastapi import Request
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.responses import JSONResponse


def custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    slowapi_response = _rate_limit_exceeded_handler(request, exc)
    
    retry_after = slowapi_response.headers.get("Retry-After")
    #recalculate headers
    headers = {
        key : value 
        for key, value in slowapi_response.headers.items() 
        if key.lower() 
        not in {
            "content-length",
            "content-type",
            "content-encoding",
            "etag"
        }
    }
    
    return JSONResponse(
        status_code=429,
        content={
            "message": "To many request please try again later.",
            "detail": f"Rate limit exceeded: {exc.detail}", 
            "retry_after": int(retry_after) if retry_after is not None else None
        },
        headers=headers
    )
