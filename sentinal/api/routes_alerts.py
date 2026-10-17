from fastapi import APIRouter, Request, Depends
from sentinal.explain import build_card, render
from sentinal.alerts.workflow import alert_from_card
from .security import require_role
router=APIRouter()
@router.get('/alerts')
def alerts(request:Request,page:int=1,limit:int=50):
 a=request.app.state.store.alerts; limit=min(max(limit,1),100); page=max(page,1); start=(page-1)*limit; return {'items':a[start:start+limit],'page':page,'limit':limit,'total':len(a)}
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
            return {'alert_id': alert_id, **alert.get('explanation', {'what': alert.get('what', ''), 'why': alert.get('reasons', [])})}
    from .errors import ApiError
    raise ApiError('ALERT_NOT_FOUND', 'alert not found', {'id': alert_id}, 404)
def _why_not_payload(alert: dict, zone: str | None = None) -> dict:
    exp = alert.get('explanation') or {}
    provenance = exp.get('provenance') or []
    if not exp and not provenance:
        return {'why_not': 'insufficient-evidence', 'limitation': 'No stored risk or factor data is available.'}
    score = float(alert.get('risk_score', 0) or 0)
    factors = exp.get('factors') or {}
    selected = [(p, float(factors.get(p.get('factor'), 0))) for p in provenance if not zone or p.get('factor') == zone]
    if zone and not selected:
        return {'why_not': 'insufficient-evidence', 'limitation': f'No stored factor data for {zone}.'}
    threshold = 60.0
    if score >= threshold:
        return {'why_not': 'threshold-met', 'comparison': {'score': score, 'threshold': threshold, 'delta': score-threshold}}
    gaps = exp.get('data_gaps') or []
    return {'why_not': 'threshold-not-met', 'comparison': {'score': score, 'threshold': threshold, 'delta': score-threshold},
            'limitation': '; '.join(gaps) if gaps else None, 'factors': selected}

@router.get('/alerts/{alert_id}/why-not')
def why_not(request: Request, alert_id:str):
    alert = next((a for a in request.app.state.store.alerts if a.get('id') == alert_id), None)
    if not alert: return {'alert_id': alert_id, 'why_not': 'insufficient-evidence', 'limitation': 'Alert not found'}
    return {'alert_id': alert_id, **_why_not_payload(alert)}
@router.get('/alerts/{alert_id}/why-not/{zone}')
def why_not_zone(request: Request, alert_id: str, zone: str):
    alert = next((a for a in request.app.state.store.alerts if a.get('id') == alert_id), None)
    payload = _why_not_payload(alert or {}, zone)
    return {'alert_id': alert_id, 'zone': zone, **payload}
@router.patch('/alerts/{alert_id}')
def update_alert(request: Request, alert_id: str, payload: dict, _: str = Depends(require_role('admin', 'operator'))):
    for alert in request.app.state.store.alerts:
        if alert.get('id') != alert_id:
            continue
        if 'status' in payload:
            current = alert.get('status', 'New')
            target = payload['status']
            allowed = {'New': {'Acknowledged', 'False Positive'}, 'Acknowledged': {'Assigned', 'Resolved', 'False Positive'}, 'Assigned': {'Resolved', 'False Positive'}, 'Resolved': set(), 'False Positive': set()}
            if target not in allowed.get(current, set()):
                from .errors import ApiError
                raise ApiError('INVALID_ALERT_TRANSITION', f'invalid transition {current} -> {target}', {'allowed': sorted(allowed.get(current, set()))})
            alert['status'] = target
        if 'assignee' in payload:
            alert['assignee'] = payload['assignee']
        if 'feedback' in payload:
            alert['feedback'] = payload['feedback']
        request.app.state.store.save_alert(alert)
        request.app.state.store.persistence.audit('alert.update', {'alert_id': alert_id, 'changes': payload}, getattr(request.state, 'correlation_id', None))
        return alert
    from .errors import ApiError
    raise ApiError('ALERT_NOT_FOUND', 'alert not found', {'id': alert_id}, 404)
