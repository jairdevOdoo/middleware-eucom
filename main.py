import asyncio
import json
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from config import validate_token, logging

app = FastAPI(title="Gateway Central Odoo-Alvic")
logger = logging.getLogger("gateway")

# --- GESTOR DEL ESTADO EN MEMORIA ---
class ConnectionManager:
    def __init__(self):
        # Almacenamiento en Memoria (RAM) establecido en la arquitectura
        self.active_tunnels: dict[str, WebSocket] = {}
        self.pending_requests: dict[str, asyncio.Future] = {}

    async def connect(self, station_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_tunnels[station_id] = websocket
        logger.info("WebSocket conectado | station_id=%s", station_id)

    def disconnect(self, station_id: str):
        if station_id in self.active_tunnels:
            del self.active_tunnels[station_id]
            logger.info("WebSocket desconectado | station_id=%s", station_id)

manager = ConnectionManager()

# --- 1. ENDPOINT WEBSOCKET (Para los Agentes Locales) ---
@app.websocket("/ws/{station_id}")
async def websocket_endpoint(websocket: WebSocket, station_id: str):
    """Recibe la conexión entrante desde el .exe de la gasolinera."""
    # Validación de seguridad individual del Agente
    auth_header = websocket.headers.get("authorization", "")
    if not validate_token(station_id, auth_header):
        logger.warning("WebSocket rechazado: token inválido | station_id=%s", station_id)
        await websocket.close(code=1008)
        return

    await manager.connect(station_id, websocket)
    try:
        while True:
            # Escucha permanentemente las respuestas que el Agente manda de regreso
            message = await websocket.receive_text()
            data = json.loads(message)
            request_id = data.get("request_id")
            
            # Resuelve la promesa (Future) de la petición HTTP que estaba pausada esperando esto
            if request_id and request_id in manager.pending_requests:
                future = manager.pending_requests[request_id]
                if not future.done():
                    future.set_result(data)
                    logger.info( "Respuesta recibida del agente | station_id=%s request_id=%s status_code=%s",
                        station_id, request_id, data.get("status_code", 200), )
            else:
                logger.warning("Respuesta WebSocket sin petición pendiente | station_id=%s request_id=%s",
                                                                                station_id, request_id,)
                    
    except WebSocketDisconnect:
        manager.disconnect(station_id)
    except json.JSONDecodeError:
        logger.warning("Mensaje WebSocket no es JSON válido | station_id=%s", station_id)
        manager.disconnect(station_id)
    except Exception:
        logger.exception("Error no controlado en WebSocket | station_id=%s", station_id)
        manager.disconnect(station_id)

# --- 2. ENDPOINT REST (Para Odoo 19 SH) ---
@app.api_route("/api/v1/{station_id}/{path:path}", methods=["GET", "POST", "PUT"])
async def proxy_from_odoo(station_id: str,path:str,request: Request,x_station_token: str = Header(None)):
    """Odoo consume esta ruta. Ej: GET /api/v1/estacion_01/ventas"""
    
    # 1. Validación de seguridad individual usando el nuevo header
    if not validate_token(station_id, x_station_token): # <-- CAMBIO AQUÍ
        logger.warning("Solicitud HTTP rechazada: token inválido | station_id=%s method=%s path=/%s client=%s",station_id,
                                    request.method,path,request.client.host if request.client else "unknown",)
        raise HTTPException(status_code=401, detail="No autorizado. Token de estación inválido.")
        
    if station_id not in manager.active_tunnels:
        logger.warning("Solicitud HTTP rechazada: estación desconectada | station_id=%s method=%s path=/%s",
                                                        station_id,request.method, path,)
        raise HTTPException(status_code=503, detail="Estación desconectada de la red.")
    # 2. Multiplexación: Generar Correlation ID (UUID)
    request_id = str(uuid.uuid4())
    body = await request.json() if request.method in ["POST", "PUT"] else {}
    
    # Extraemos los headers de Odoo (Aquí viene el Bearer token dinámico de Alvic)
    odoo_headers = dict(request.headers)
    # Removemos headers de host/conexión que pueden causar conflictos en la red local
    odoo_headers.pop("host", None) 

    endpoint = f"/{path}"
    if request.url.query:
        endpoint = f"{endpoint}?{request.url.query}"

    payload = {"request_id": request_id,"endpoint": endpoint,"method": request.method,"data": body,"headers": odoo_headers}

    # 3. Crear el asyncio.Future para pausar la respuesta HTTP
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    manager.pending_requests[request_id] = future

    # 4. Enviar instrucción al Agente
    ws = manager.active_tunnels[station_id]
    logger.info("Solicitud enviada al agente | station_id=%s request_id=%s method=%s endpoint=%s",station_id,
                                                                        request_id,
                                                                        request.method,
                                                                        endpoint,
                                                                    )
    try:
        await ws.send_text(json.dumps(payload))
    except Exception:
        logger.exception(
            "No se pudo enviar solicitud al agente | station_id=%s request_id=%s",
            station_id,
            request_id,
        )
        raise HTTPException(status_code=502, detail="No se pudo comunicar con la estación.")

    # 5. Timeout Rígido y Respuesta
    try:
        # FastAPI espera hasta 15s. Si el Agente devuelve el resultado por el WSS, continúa.
        respuesta = await asyncio.wait_for(future, timeout=120.0) 
        status = respuesta.get("status_code", 200)
        logger.info("Solicitud HTTP completada | station_id=%s request_id=%s status_code=%s",station_id,request_id,
                                                                        status,)
        return JSONResponse(status_code=status, content=respuesta.get("data"))
        
    except asyncio.TimeoutError:
        # Evita que workers de Odoo queden bloqueados infinitamente
        logger.error("Timeout esperando al agente | station_id=%s request_id=%s timeout_seconds=15",station_id,
                                                                                                    request_id,)
        raise HTTPException(status_code=504, detail="Gateway Timeout: La estación no respondió a tiempo.")
    finally:
        if request_id in manager.pending_requests:
            del manager.pending_requests[request_id]

# --- 3. ENDPOINT SALUD (Monitoreo) ---
@app.get("/health")
async def health_check():
    """Permite saber cuántas y cuáles estaciones están conectadas."""
    return {"status": "online","active_tunnels_count": len(manager.active_tunnels),"connected_stations": list(manager.active_tunnels.keys())}