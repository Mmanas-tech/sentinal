from fastapi import APIRouter, Request
router=APIRouter()
@router.post('/telemetry/validate')
def validate(request: Request, payload: dict):
 r=request.app.state.store.telemetry.validate(payload); return r.model_dump()
