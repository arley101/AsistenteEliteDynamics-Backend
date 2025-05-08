# MyHttpTrigger/helpers/http_client.py
import requests
import logging
from typing import Dict, Any, Optional, Union, Tuple

# Import relativo DENTRO de MyHttpTrigger
try:
    from ..shared.constants import TIMEOUT # <-- Import relativo corregido
except ImportError:
    logging.warning("No se pudo importar TIMEOUT desde .shared.constants. Usando predeterminado.")
    TIMEOUT = 30

logger = logging.getLogger(__name__)

# ... (El resto de la función hacer_llamada_api como te la pasé antes) ...
# (Pego de nuevo por completitud)
def hacer_llamada_api(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    data: Optional[Union[Dict[str, Any], str]] = None,
    expected_status: int = 200,
    return_type: str = "json" # Opciones: "json", "text", "bytes", "response"
) -> Tuple[Optional[Any], Optional[str]]:
    request_id = headers.get("X-Request-ID", "N/A") if headers else "N/A"
    logger.info(f"ReqID {request_id}: Realizando llamada API: {method} {url}")
    # ... (resto de la lógica de http_client sin cambios) ...
    # ... (manejo de errores, logs, etc.) ...
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_data,
            data=data,
            timeout=TIMEOUT
        )
        # Intenta obtener detalles del error incluso si raise_for_status falla
        response_text_for_error = ""
        try:
            response_text_for_error = response.text
        except Exception:
            pass # Ignora si no se puede leer el texto

        response.raise_for_status() # Lanza HTTPError para respuestas 4xx/5xx

        # Código original para éxito (2xx pero no necesariamente expected_status)
        # Se ajusta para que funcione si expected_status no es 200 OK pero sí éxito (ej 201, 202, 204)
        if response.status_code == expected_status or (200 <= response.status_code < 300 and expected_status < 300) :
            status_to_log = response.status_code if response.status_code == expected_status else f"{response.status_code} (esperado {expected_status})"
            logger.info(f"ReqID {request_id}: Llamada API exitosa ({status_to_log}).")
            # Manejar caso 204 No Content
            if response.status_code == 204:
                return {"status": "success", "code": 204, "message": "No Content"}, None

            # Procesar otros éxitos
            if return_type == "json":
                try:
                    return response.json(), None
                except requests.exceptions.JSONDecodeError:
                    logger.warning(f"ReqID {request_id}: La respuesta de {url} no es JSON válido aunque el status es {response.status_code}. Devolviendo texto.")
                    return response.text, None
            elif return_type == "text":
                return response.text, None
            elif return_type == "bytes":
                return response.content, None
            elif return_type == "response":
                return response, None
            else:
                 logger.error(f"ReqID {request_id}: Tipo de retorno no válido especificado: {return_type}")
                 return None, f"Error interno: Tipo de retorno no válido '{return_type}'"
        else:
             # Caso raro: Status < 300 pero no coincide con expected_status
             error_msg = f"Respuesta inesperada ({response.status_code}) pero exitosa: {response_text_for_error}"
             logger.warning(f"ReqID {request_id}: {error_msg}")
             # Decide si devolver esto como éxito o error; devolvamos como error por claridad
             return None, error_msg

    except requests.exceptions.HTTPError as http_err:
        # Error 4xx/5xx
        status_code = http_err.response.status_code
        error_msg = f"Error HTTP {status_code} en llamada API ({type(http_err).__name__}) a {url}: {response_text_for_error}"
        logger.error(f"ReqID {request_id}: {error_msg}")
        # Intenta extraer detalles del JSON si existe
        try:
            error_details = http_err.response.json()
            error_msg_detail = f"{error_msg} | Detalles: {json.dumps(error_details)}"
        except:
             error_msg_detail = error_msg # Mantener el texto si no hay JSON
        return None, error_msg_detail

    except requests.exceptions.RequestException as req_err:
        error_msg = f"Error en la llamada API ({type(req_err).__name__}) a {url}: {req_err}"
        logger.error(f"ReqID {request_id}: {error_msg}")
        return None, f"Error de conexión o solicitud: {req_err}"
    except Exception as e:
        error_msg = f"Error inesperado procesando la llamada API a {url}: {e}"
        logger.exception(f"ReqID {request_id}: {error_msg}") # Loguea el traceback completo
        return None, f"Error inesperado: {e}"