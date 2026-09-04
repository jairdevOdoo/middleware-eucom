import os
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


AUTHORIZED_TOKENS = {
    "estacion_01": os.getenv("TOKEN_ESTACION_01"),
    "estacion_02": os.getenv("TOKEN_ESTACION_02")
}

def validate_token(station_id: str, token_provided: str) -> bool:
    """Valida si el token enviado (por Odoo o el Agente) pertenece a la estación solicitada."""
    expected_token = AUTHORIZED_TOKENS.get(station_id)
    if not expected_token or not token_provided:
        return False
    # Remueve el prefijo 'Bearer ' si existe
    clean_token = token_provided.replace("Bearer ", "").strip()
    return clean_token == expected_token