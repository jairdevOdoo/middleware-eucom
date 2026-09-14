import os
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


AUTHORIZED_TOKENS = {
    "estacion_01": os.getenv("TOKEN_ESTACION_01"),
    "estacion_02": os.getenv("TOKEN_ESTACION_02"),
    "estacion_03": os.getenv("TOKEN_ESTACION_03"),
    "estacion_04": os.getenv("TOKEN_ESTACION_04"),
    "estacion_05": os.getenv("TOKEN_ESTACION_05"),
    "estacion_06": os.getenv("TOKEN_ESTACION_06"),
    "estacion_07": os.getenv("TOKEN_ESTACION_07"),
    "estacion_08": os.getenv("TOKEN_ESTACION_08"),
    "estacion_09": os.getenv("TOKEN_ESTACION_09"),
    "estacion_10": os.getenv("TOKEN_ESTACION_10"),
    "estacion_11": os.getenv("TOKEN_ESTACION_11"),
    "estacion_12": os.getenv("TOKEN_ESTACION_12"),
    "estacion_13": os.getenv("TOKEN_ESTACION_13")
}

def validate_token(station_id: str, token_provided: str) -> bool:
    """Valida si el token enviado (por Odoo o el Agente) pertenece a la estación solicitada."""
    expected_token = AUTHORIZED_TOKENS.get(station_id)
    if not expected_token or not token_provided:
        return False
    # Remueve el prefijo 'Bearer ' si existe
    clean_token = token_provided.replace("Bearer ", "").strip()
    return clean_token == expected_token