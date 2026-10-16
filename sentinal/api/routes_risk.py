from fastapi import APIRouter, Request
from .errors import ApiError
router=APIRouter()
def result(r, asset, factors, what=False):
 try: x=(r.what_if if what else r.evaluate)(asset, factors); return x.__dict__
 except Exception as e: raise ApiError('RISK_INVALID',str(e))
@router.get('/risk/assets')
def assets(request: Request, page:int=1, limit:int=50):
 vals=[a.__dict__ for a in request.app.state.store.risk.registry]; limit=min(max(limit,1),100); start=(max(page,1)-1)*limit
 return {'items':vals[start:start+limit],'page':page,'limit':limit,'total':len(vals)}
@router.post('/risk/whatif')
def whatif(request: Request, payload:dict): return result(request.app.state.store.risk,payload.get('asset_id'),payload.get('factors',{}),True)
