# MyHttpTrigger/actions/openai_actions.py
import logging
import requests # Solo para tipos de excepción
import json
import os
from typing import Dict, List, Optional, Any

# Importar helper y constantes
try:
    from ..shared.helpers.http_client import hacer_llamada_api
    from ..shared.constants import (
        APP_NAME,
        AZURE_OPENAI_ENDPOINT, # Endpoint base de tu recurso AOAI
        AZURE_OPENAI_API_VERSION, # Versión de API que usa tu despliegue
        DEFAULT_API_TIMEOUT # Timeout base, podemos ajustarlo
    )
except ImportError as e:
    logging.critical(f"Error CRÍTICO importando dependencias compartidas en OpenAI: {e}.", exc_info=True)
    APP_NAME = "EliteDynamicsPro" # Fallback
    AZURE_OPENAI_ENDPOINT = None
    AZURE_OPENAI_API_VERSION = "2024-02-01" # Fallback version
    DEFAULT_API_TIMEOUT = 60 # Fallback timeout
    raise ImportError(f"No se pudo importar 'hacer_llamada_api' o constantes AOAI: {e}") from e

logger = logging.getLogger(f"{APP_NAME}.actions.openai")

# Validar configuración esencial al cargar el módulo
if not AZURE_OPENAI_ENDPOINT:
    msg = "Variable de entorno 'AZURE_OPENAI_ENDPOINT' no configurada. Las acciones de OpenAI no funcionarán."
    logger.critical(msg)
    # Podríamos lanzar un error aquí para prevenir carga parcial
    # raise ValueError(msg)

# Timeout más largo por defecto para llamadas a OpenAI
OPENAI_API_TIMEOUT = max(DEFAULT_API_TIMEOUT, 120) # Ej: 2 minutos por defecto

# ---- FUNCIONES DE ACCIÓN PARA AZURE OPENAI ----
# Asumen autenticación AAD (token Bearer en headers)

def openai_chat_completion(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Genera una respuesta de chat usando un modelo desplegado en Azure OpenAI.

    Args:
        parametros (Dict[str, Any]):
            'deployment_id' (str): Nombre del despliegue del modelo de chat (ej. 'gpt-4', 'gpt-35-turbo'). Requerido.
            'messages' (List[Dict]): Lista de mensajes en formato OpenAI (ej. [{'role': 'user', 'content': 'Hola'}]). Requerido.
            'temperature' (float, opcional): Controla la aleatoriedad (0.0 a 2.0). Default ~0.7.
            'max_tokens' (int, opcional): Máximo de tokens a generar en la respuesta.
            'stop' (Union[str, List[str]], opcional): Secuencia(s) para detener la generación.
            'stream' (bool, opcional): Si se desea respuesta en stream (no soportado directamente por esta función, devuelve error). Default False.
            # ... otros parámetros de la API de Chat Completion ...
        headers (Dict[str, str]): Cabeceras con el token AAD para Azure OpenAI.

    Returns:
        Dict[str, Any]: {"status": "success", "data": {respuesta_openai}} o error.
    """
    deployment_id: Optional[str] = parametros.get("deployment_id")
    messages: Optional[List[Dict[str, str]]] = parametros.get("messages")
    # Validar parámetros requeridos
    if not deployment_id: return {"status": "error", "message": "Parámetro 'deployment_id' (nombre del despliegue OpenAI) es requerido."}
    if not messages or not isinstance(messages, list) or not all(isinstance(m, dict) and 'role' in m and 'content' in m for m in messages):
        return {"status": "error", "message": "Parámetro 'messages' (lista de {'role': '...', 'content': '...'}) es requerido y debe tener formato válido."}
    if not AZURE_OPENAI_ENDPOINT: return {"status": "error", "message": "Configuración incompleta: AZURE_OPENAI_ENDPOINT no está definido."}

    # Validar que no se pida stream (no soportado en este helper simple)
    if parametros.get("stream", False):
        return {"status": "error", "message": "El modo 'stream' no está soportado por esta acción actualmente."}

    # Construir URL y payload
    # Ej: https://<resource>.openai.azure.com/openai/deployments/<deployment-id>/chat/completions?api-version=<version>
    url = f"{AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/deployments/{deployment_id}/chat/completions?api-version={AZURE_OPENAI_API_VERSION}"
    
    # Construir cuerpo solo con parámetros relevantes para la API
    payload: Dict[str, Any] = {"messages": messages}
    allowed_params = ["temperature", "max_tokens", "top_p", "frequency_penalty", "presence_penalty", "stop", "logit_bias", "user"]
    for param, value in parametros.items():
        if param in allowed_params and value is not None:
            payload[param] = value

    logger.info(f"Enviando petición de Chat Completion a despliegue '{deployment_id}' ({len(messages)} mensajes)")
    logger.debug(f"Payload Chat Completion (sin messages): { {k:v for k,v in payload.items() if k != 'messages'} }")
    
    try:
        # Timeout más largo para posibles respuestas largas
        response_data = hacer_llamada_api("POST", url, headers, json_data=payload, timeout=OPENAI_API_TIMEOUT)
        # La respuesta exitosa usualmente tiene 'choices', 'usage', etc.
        return {"status": "success", "data": response_data}
    except Exception as e:
        logger.error(f"Error en Chat Completion con despliegue '{deployment_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error en Chat Completion: {type(e).__name__}", "http_status": status_code, "details": details}


def openai_get_embeddings(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Genera embeddings para un texto de entrada usando un modelo desplegado en Azure OpenAI.

    Args:
        parametros (Dict[str, Any]):
            'deployment_id' (str): Nombre del despliegue del modelo de embeddings (ej. 'text-embedding-ada-002'). Requerido.
            'input' (Union[str, List[str]]): El texto o lista de textos para generar embeddings. Requerido.
            'user' (str, opcional): Identificador del usuario final para monitorización.
        headers (Dict[str, str]): Cabeceras con el token AAD para Azure OpenAI.

    Returns:
        Dict[str, Any]: {"status": "success", "data": {respuesta_openai_embeddings}} o error.
    """
    deployment_id: Optional[str] = parametros.get("deployment_id")
    input_data: Optional[Union[str, List[str]]] = parametros.get("input")
    user_param: Optional[str] = parametros.get("user") # Parámetro opcional 'user' de la API

    if not deployment_id: return {"status": "error", "message": "Parámetro 'deployment_id' (nombre del despliegue OpenAI Embeddings) es requerido."}
    if not input_data: return {"status": "error", "message": "Parámetro 'input' (string o lista de strings) es requerido."}
    if not AZURE_OPENAI_ENDPOINT: return {"status": "error", "message": "Configuración incompleta: AZURE_OPENAI_ENDPOINT no está definido."}

    # Construir URL y payload
    url = f"{AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/deployments/{deployment_id}/embeddings?api-version={AZURE_OPENAI_API_VERSION}"
    payload: Dict[str, Any] = {"input": input_data}
    if user_param: payload["user"] = user_param
    
    input_type = "lista" if isinstance(input_data, list) else "string"
    logger.info(f"Generando Embeddings con despliegue '{deployment_id}' para entrada tipo '{input_type}'")
    
    try:
        response_data = hacer_llamada_api("POST", url, headers, json_data=payload, timeout=OPENAI_API_TIMEOUT)
        # La respuesta exitosa tiene 'data' (lista de embeddings), 'model', 'usage'.
        return {"status": "success", "data": response_data}
    except Exception as e:
        logger.error(f"Error generando Embeddings con despliegue '{deployment_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error en Embeddings: {type(e).__name__}", "http_status": status_code, "details": details}

# --- Aquí se podrían añadir más acciones para OpenAI ---
# Ejemplo: openai_generate_image (requiere API diferente y manejo asíncrono a veces)
# Ejemplo: openai_transcribe_audio (requiere manejar datos binarios de audio)

# --- FIN DEL MÓDULO actions/openai_actions.py ---