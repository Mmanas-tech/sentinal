from fastapi import Request
from fastapi.responses import JSONResponse

class ApiError(Exception):
    def __init__(self, code: str, message: str, details=None, status_code: int = 400):
        self.code, self.message, self.details, self.status_code = code, message, details, status_code

def error_response(code, message, details=None, status_code=400):
    return JSONResponse(status_code=status_code, content={'error': {'code': code, 'message': message, 'details': details}})

async def api_error_handler(request: Request, exc: ApiError):
    return error_response(exc.code, exc.message, exc.details, exc.status_code)

async def validation_error_handler(request: Request, exc):
    return error_response('VALIDATION_ERROR', 'invalid request', getattr(exc, 'errors', lambda: None)(), 422)
