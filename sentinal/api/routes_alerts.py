from fastapi import APIRouter, Request
from sentinal.explain import build_card, render
from sentinal.alerts.workflow import alert_from_card
router=APIRouter()
@router.get('/alerts')
def alerts(request:Request,page:int=1,limit:int=50):
 a=request.app.state.store.alerts; start=(max(page,1)-1)*limit; return {'items':a[start:start+limit],'page':page,'limit':limit,'total':len(a)}
@router.get('/alerts/explanation/{alert_id}')
def explanation(request: Request, alert_id: str):
    for alert in request.app.state.store.alerts:
        if alert.get('id') == alert_id:
            return {'alert_id': alert_id, 'explanation': alert.get('explanation', {})}
    from .errors import ApiError
    raise ApiError('ALERT_NOT_FOUND', 'alert not found', {'id': alert_id}, 404)
@router.get('/alerts/{alert_id}/explanation')
def explanation_canonical(request: Request, alert_id: str):
    for alert in request.app.state.store.alerts:
        if alert.get('id') == alert_id:
            return alert.get('explanation', {'alert_id': alert_id, 'what': alert.get('what', ''), 'why': alert.get('reasons', [])})
    return {'alert_id':alert_id,'explanation':'Explanation snapshot unavailable','data_gaps':['alert not found']}
@router.get('/alerts/{alert_id}/why-not')
def why_not(alert_id:str): return {'alert_id':alert_id,'why_not':'Insufficient evidence or threshold not met'}
@router.get('/alerts/{alert_id}/why-not/{zone}')
def why_not_zone(alert_id: str, zone: str):
    return {'alert_id': alert_id, 'zone': zone, 'why_not': 'No stored factor exceeded the configured alert threshold.'}
@router.patch('/alerts/{alert_id}')
def update_alert(request: Request, alert_id: str, payload: dict):
    for alert in request.app.state.store.alerts:
        if alert.get('id') != alert_id:
            continue
        if 'status' in payload:
            alert['status'] = payload['status']
        if 'assignee' in payload:
            alert['assignee'] = payload['assignee']
        if 'feedback' in payload:
            alert['feedback'] = payload['feedback']
        return alert
    from .errors import ApiError
    raise ApiError('ALERT_NOT_FOUND', 'alert not found', {'id': alert_id}, 404)
