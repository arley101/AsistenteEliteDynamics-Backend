# MyHttpTrigger/shared/helpers/http_client.py
import logging
import requests
import time
import json
from typing import Dict, Any, Optional, Union

try:
    from ..constants import DEFAULT_API_TIMEOUT, APP_NAME, APP_VERSION
except ImportError: # Fallback para pruebas aisladas o linters
    DEFAULT_API_TIMEOUT = 45
    APP_NAME = "EliteDynamicsProHelper"
    APP_VERSION = "1.0.0"

logger = logging.getLogger(f"{APP_NAME}.http_client")

# --- Configuración de Reintentos ---
# Puedes hacerla más configurable si lo deseas (ej. desde env vars)
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY_SECONDS = 2 # Espera base
MAX_RETRY_DELAY_SECONDS = 30  # Espera máxima para no bloquear indefinidamente

def hacer_llamada_api(
    metodo: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    data: Optional[Union[bytes, str, Dict[str, Any]]] = None, # Puede ser bytes, string, o dict para form-data
    params: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
    expect_json: bool = True,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_retry_delay: int = DEFAULT_RETRY_DELAY_SECONDS,
    stream: bool = False # Para descargar archivos grandes
) -> Union[Dict[str, Any], requests.Response, bytes, None]:
    """
    Helper centralizado para realizar llamadas HTTP a APIs.
    Incluye User-Agent, manejo de errores, y reintentos con backoff exponencial simple.

    Args:
        metodo (str): Método HTTP (GET, POST, PUT, PATCH, DELETE).
        url (str): URL completa del endpoint.
        headers (Optional[Dict[str, str]]): Cabeceras HTTP. 'Authorization' es clave.
        json_data (Optional[Dict[str, Any]]): Payload JSON.
        data (Optional[Union[bytes, str, Dict[str, Any]]]): Payload para bytes, string, o form-data.
        params (Optional[Dict[str, Any]]): Parámetros de query string.
        timeout (Optional[int]): Timeout específico. Usa default si es None.
        expect_json (bool): True para parsear respuesta JSON, False para devolver objeto Response.
                             Si stream=True, expect_json se ignora para el cuerpo principal.
        max_retries (int): Máximo número de reintentos.
        base_retry_delay (int): Segundos base para la espera entre reintentos.
        stream (bool): Si es True, la respuesta se procesa como stream (para descargas).
                       En este caso, la función devuelve bytes si es exitosa.

    Returns:
        - Dict si expect_json es True y la respuesta es JSON.
        - requests.Response si expect_json es False (y stream es False) y la llamada es 2xx.
        - bytes si stream es True y la llamada es 2xx.
        - None si la respuesta es 204 No Content.
        - Lanza requests.exceptions.RequestException para errores no recuperables.
    """
    final_headers = headers.copy() if headers else {}
    final_headers.setdefault('User-Agent', f"{APP_NAME}/{APP_VERSION}")

    # Asegurar Content-Type si se envía JSON y no se especifica explícitamente en data
    if json_data and not data and 'Content-Type' not in final_headers:
        final_headers['Content-Type'] = 'application/json'
    # Si 'data' es un dict y no hay Content-Type, requests lo enviará como form-urlencoded
    # Si 'data' son bytes, el Content-Type debe ser seteado por el llamador (ej. application/octet-stream)

    effective_timeout = timeout if timeout is not None else DEFAULT_API_TIMEOUT

    for attempt in range(max_retries + 1):
        current_delay = min(base_retry_delay * (2 ** attempt), MAX_RETRY_DELAY_SECONDS) # Backoff exponencial con tope
        try:
            logger.debug(f"API Call (Attempt {attempt + 1}/{max_retries + 1}): {metodo.upper()} {url}")
            if params: logger.debug(f" Query Params: {params}")
            # Loguear payload con cuidado de no exponer demasiada info o datos binarios largos
            if json_data: logger.debug(f" JSON Payload (preview): {str(json_data)[:500]}")
            elif isinstance(data, bytes): logger.debug(f" Bytes Payload Length: {len(data)}")
            elif data: logger.debug(f" Data Payload (preview): {str(data)[:200]}")

            response = requests.request(
                method=metodo.upper(),
                url=url,
                headers=final_headers,
                json=json_data if not data and isinstance(json_data, dict) else None,
                data=data,
                params=params,
                timeout=effective_timeout,
                stream=stream # Pasar el flag de stream a requests
            )

            logger.debug(f"API Response: {response.status_code} {response.reason} from {response.url}")

            # Manejo de errores y reintentos
            # 429 (Too Many Requests), 500, 502 (Bad Gateway), 503 (Service Unavailable), 504 (Gateway Timeout)
            if response.status_code in [429, 500, 502, 503, 504]:
                error_type = "Rate limit (429)" if response.status_code == 429 else f"Server error ({response.status_code})"
                # Usar el header Retry-After si está disponible para 429
                sleep_duration = current_delay
                if response.status_code == 429:
                    retry_after_header = response.headers.get("Retry-After")
                    if retry_after_header:
                        try:
                            sleep_duration = int(retry_after_header)
                            sleep_duration = min(sleep_duration, MAX_RETRY_DELAY_SECONDS) # Respetar tope
                        except ValueError:
                            logger.warning(f"Retry-After header ('{retry_after_header}') no es un entero. Usando delay calculado.")
                
                logger.warning(f"{error_type} en {url}. Reintentando en {sleep_duration}s... (Intento {attempt + 1})")
                
                if attempt < max_retries:
                    time.sleep(sleep_duration)
                    continue # Reintentar
                else:
                    logger.error(f"Máximos reintentos ({max_retries}) alcanzados por {error_type.lower()} en {url}.")
                    response.raise_for_status() # Lanza la excepción final

            # Errores de cliente (4xx) no reintentables (excepto 429 ya manejado)
            # o errores de servidor (5xx) que no fueron reintentados o fallaron todos los reintentos
            response.raise_for_status() # Lanza HTTPError para estos casos

            # Procesar respuesta exitosa (2xx)
            if response.status_code == 204: # No Content
                logger.info(f"Llamada exitosa a {url} (204 No Content).")
                return None

            if stream: # Si es stream, devolver el contenido en bytes
                logger.info(f"Descargando contenido en stream de {url}...")
                # Aquí podríamos iterar sobre response.iter_content() si el archivo es muy grande
                # y escribir a un archivo temporal o en memoria, pero para la mayoría de los casos
                # response.content será suficiente si no son GBs.
                # Para Graph API, el contenido del archivo suele ser la respuesta directa.
                file_bytes = response.content
                logger.info(f"Stream descargado, {len(file_bytes)} bytes.")
                return file_bytes

            if expect_json:
                try:
                    return response.json()
                except json.JSONDecodeError as json_err:
                    logger.error(f"Error decodificando JSON de {url} (Status: {response.status_code}): {json_err}. Texto: {response.text[:500]}", exc_info=True)
                    raise requests.exceptions.JSONDecodeError(f"Fallo al decodificar JSON de API: {json_err}", response.text, response.status_code) from json_err
            else:
                return response # Devolver el objeto Response completo

        except requests.exceptions.Timeout as timeout_err:
            logger.error(f"Timeout en API Call (Intento {attempt + 1}): {metodo.upper()} {url} ({effective_timeout}s). Error: {timeout_err}", exc_info=True)
            if attempt < max_retries: time.sleep(current_delay); continue
            else: logger.error(f"Máximos reintentos por Timeout en {url}."); raise
        except requests.exceptions.ConnectionError as conn_err:
            logger.error(f"Error de Conexión en API Call (Intento {attempt + 1}): {metodo.upper()} {url}. Error: {conn_err}", exc_info=True)
            if attempt < max_retries: time.sleep(current_delay); continue
            else: logger.error(f"Máximos reintentos por Error de Conexión en {url}."); raise
        except requests.exceptions.RequestException as req_err:
            # Captura otros errores de requests (HTTPError, etc.) que no son reintentables por el bucle
            logger.error(f"Error de Request no reintentable en API Call: {metodo.upper()} {url}. Error: {req_err}", exc_info=True)
            if req_err.response is not None:
                 try:
                     error_body = req_err.response.json()
                     logger.error(f" Cuerpo del error API ({req_err.response.status_code}): {json.dumps(error_body, indent=2)}")
                 except json.JSONDecodeError:
                     logger.error(f" Cuerpo del error API ({req_err.response.status_code}) (no es JSON): {req_err.response.text[:500]}")
            raise # Re-lanzar la excepción original

    # Si se agotan los reintentos sin éxito (esto no debería alcanzarse si raise_for_status se usa bien)
    logger.critical(f"Todos los reintentos fallaron para {metodo.upper()} {url}.")
    # Considerar lanzar una excepción personalizada aquí
    raise requests.exceptions.RequestException(f"Todos los reintentos fallaron para {metodo.upper()} {url}")