from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/stream")
async def stream(ws: WebSocket):
    await ws.accept()
    store = ws.app.state.store
    store.websocket_clients.add(ws)
    try:
        since = ws.query_params.get("since")
        events = list(store.events)
        if since is not None:
            cursor = int(since)
            if cursor < 0 or cursor > len(events):
                await ws.close(code=1008, reason="since cursor out of range")
                return
            events = events[cursor:]
        await ws.send_json({"type": "status", "data": store.ingestion_status()})
        for index, event in enumerate(events):
            await ws.send_json({"type": "event", "cursor": index, "data": event, "status": store.ingestion_status()})
        while True:
            message = await ws.receive_json()
            if message.get("type") == "backfill":
                limit = int(message.get("limit", 50))
                if limit < 1 or limit > 500:
                    await ws.send_json(
                        {
                            "type": "error",
                            "code": "INVALID_BACKFILL_LIMIT",
                            "message": "limit must be between 1 and 500",
                        }
                    )
                    continue
                for index, event in enumerate(list(store.events)[-limit:]):
                    await ws.send_json({"type": "event", "cursor": index, "data": event, "status": store.ingestion_status()})
            else:
                await ws.send_json(
                    {
                        "type": "error",
                        "code": "INVALID_MESSAGE",
                        "message": "unsupported websocket message",
                    }
                )
    except (WebSocketDisconnect, ValueError, TypeError):
        return
    finally:
        store.websocket_clients.discard(ws)
