from fastapi import APIRouter, WebSocket, WebSocketDisconnect
router=APIRouter()
@router.websocket('/ws/stream')
async def stream(ws:WebSocket):
 await ws.accept(); store=ws.app.state.store
 try:
  since=ws.query_params.get('since'); events=list(store.events)
  if since:
   try: events=events[int(since):]
   except ValueError: pass
  for i,e in enumerate(events): await ws.send_json({'type':'event','cursor':i,'data':e})
  while True:
   msg=await ws.receive_json()
   if msg.get('type')=='backfill':
    for i,e in enumerate(list(store.events)[-min(int(msg.get('limit',50)),500):]): await ws.send_json({'type':'event','cursor':i,'data':e})
 except (WebSocketDisconnect, ValueError, TypeError): return
