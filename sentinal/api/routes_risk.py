from fastapi import APIRouter, Request
from .errors import ApiError
router=APIRouter()
def result(r, asset, factors, what=False):
 try: x=(r.what_if if what else r.evaluate)(asset, factors); return x.__dict__
 except Exception as e: raise ApiError('RISK_INVALID',str(e))
@router.get('/risk/assets')
def assets(request: Request, page:int=1, limit:int=50):
 alerts = {}
 for alert in request.app.state.store.alerts:
  asset_id = alert.get('asset_id')
  if asset_id:
   alerts[asset_id] = alert
 vals=[]
 for asset in request.app.state.store.risk.registry:
  value = asset.__dict__.copy()
  alert = alerts.get(asset.id)
  value['risk_score'] = float(alert.get('risk_score', 0)) if alert else 0.0
  value['risk_level'] = str(alert.get('level', 'low')).upper() if alert else 'LOW'
  value['alert_status'] = alert.get('status') if alert else None
  vals.append(value)
 limit=min(max(limit,1),100); start=(max(page,1)-1)*limit
 return {'items':vals[start:start+limit],'page':page,'limit':limit,'total':len(vals)}
@router.post('/risk/whatif')
def whatif(request: Request, payload:dict): return result(request.app.state.store.risk,payload.get('asset_id'),payload.get('factors',{}),True)
