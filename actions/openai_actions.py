# MyHttpTrigger/actions/openai_actions.py
import logging
import requests # Solo para tipos de excepción
# import json # No se usa directamente json.loads o .dumps si AuthenticatedHttpClient maneja .json()
from typing import Dict, List, Optional, Any, Union

# Importar el cliente autenticado y las constantes
from shared.helpers.http_client import AuthenticatedHttpClient
from shared import constants

logger = logging.getLogger(__name__)

# Validar configuración esencial al cargar el módulo
if not constants.AZURE_OPENAI_RESOURCE_ENDPOINT:
    msg = "CRÍTICO: Constante 'AZURE_OPENAI_RESOURCE_ENDPOINT' no configurada en shared/constants.py. Las acciones de OpenAI no funcionarán."
    logger.critical(msg)
    # Considerar lanzar un error si se prefiere un fallo rápido:
    # raise EnvironmentError(msg)
if not constants.AZURE_OPENAI_API_VERSION:
    msg = "CRÍTICO: Constante 'AZURE_OPENAI_API_VERSION' no configurada. Las acciones de OpenAI no funcionarán."
    logger.critical(msg)
    # raise EnvironmentError(msg)


# Timeout más largo por defecto para llamadas a OpenAI, configurable si es necesario.
# Usamos el DEFAULT_API_TIMEOUT de constants y lo extendemos si es necesario aquí.
# Si DEFAULT_API_TIMEOUT ya es suficientemente largo (ej. 120s), esto es redundante.
# OPENAI_CALL_TIMEOUT = max(constants.DEFAULT_API_TIMEOUT, 120)
# Por ahora, usaremos el DEFAULT_API_TIMEOUT directamente de constants, asumiendo que está configurado adecuadamente.

# ---- FUNCIONES DE ACCIÓN PARA AZURE OPENAI ----

def chat_completion(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Genera una respuesta de chat usando un modelo desplegado en Azure OpenAI.
    Nombre de función alineado con ACTION_MAP.
    """
    if not constants.AZURE_OPENAI_RESOURCE_ENDPOINT or not constants.AZURE_OPENAI_API_VERSION:
        return {"status": "error", "message": "Configuración de Azure OpenAI incompleta (endpoint o api-version).", "http_status": 500}

    deployment_id: Optional[str] = params.get("deployment_id")
    messages: Optional[List[Dict[str, str]]] = params.get("messages")
    
    if not deployment_id: 
        return {"status": "error", "message": "Parámetro 'deployment_id' (nombre del despliegue OpenAI) es requerido.", "http_status": 400}
    if not messages or not isinstance(messages, list) or not all(isinstance(m, dict) and 'role' in m and 'content' in m for m in messages):
        return {"status": "error", "message": "Parámetro 'messages' (lista de {'role': '...', 'content': '...'}) es requerido y debe tener formato válido.", "http_status": 400}
    
    # Verificar si 'stream' se solicita y manejarlo (actualmente no soportado por simplicidad en el retorno síncrono)
    if params.get("stream", False):
        logger.warning(f"Solicitud de Chat Completion para despliegue '{deployment_id}' con stream=true. Esta acción no soporta streaming actualmente y procederá de forma síncrona.")
        # No devolvemos error, simplemente ignoramos el stream para la respuesta síncrona.
        # Si fuera mandatorio soportar stream, la lógica de la función y su retorno cambiarían drásticamente.

    url = f"{constants.AZURE_OPENAI_RESOURCE_ENDPOINT.rstrip('/')}/openai/deployments/{deployment_id}/chat/completions?api-version={constants.AZURE_OPENAI_API_VERSION}"
    
    payload: Dict[str, Any] = {"messages": messages}
    
    # Parámetros opcionales permitidos por la API de Chat Completion de Azure OpenAI
    allowed_api_params = [
        "temperature", "max_tokens", "top_p", "frequency_penalty", 
        "presence_penalty", "stop", "logit_bias", "user", "n",
        "logprobs", "top_logprobs", "response_format", "seed", "tools", "tool_choice"
        # "stream" ya se manejó arriba
    ]
    for param_key, value in params.items():
        if param_key in allowed_api_params and value is not None:
            payload[param_key] = value

    logger.info(f"Enviando petición de Chat Completion a AOAI despliegue '{deployment_id}' ({len(messages)} mensajes).")
    logger.debug(f"Payload Chat Completion (sin 'messages'): { {k:v for k,v in payload.items() if k != 'messages'} }")
    
    try:
        response = client.post(
            url=url,
            scope=constants.OPENAI_SCOPE, # Scope específico para Azure OpenAI
            json_data=payload, # AuthenticatedHttpClient usa json_data
            timeout=constants.DEFAULT_API_TIMEOUT # Usar timeout global o uno específico para OpenAI
        )
        response_data = response.json()
        return {"status": "success", "data": response_data}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        logger.error(f"Error HTTP en Chat Completion AOAI '{deployment_id}': {http_err.response.status_code if http_err.response else 'N/A'} - {error_details[:500]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {http_err.response.status_code if http_err.response else 'N/A'}", "details": error_details, "http_status": http_err.response.status_code if http_err.response else 500}
    except ValueError as val_err: # Error de token del cliente o JSON malformado en respuesta
        logger.error(f"Error de Valor (auth/JSON) en Chat Completion AOAI '{deployment_id}': {val_err}", exc_info=True)
        return {"status": "error", "message": "Error de autenticación, configuración o formato de respuesta JSON.", "details": str(val_err)}
    except Exception as e:
        logger.error(f"Error inesperado en Chat Completion AOAI '{deployment_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error inesperado en Chat Completion: {type(e).__name__}", "details": str(e)}

def get_embedding(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Genera embeddings para un texto de entrada usando un modelo desplegado en Azure OpenAI.
    Nombre de función alineado con ACTION_MAP.
    """
    if not constants.AZURE_OPENAI_RESOURCE_ENDPOINT or not constants.AZURE_OPENAI_API_VERSION:
        return {"status": "error", "message": "Configuración de Azure OpenAI incompleta (endpoint o api-version).", "http_status": 500}

    deployment_id: Optional[str] = params.get("deployment_id")
    input_data: Optional[Union[str, List[str]]] = params.get("input") # La API acepta string o array de strings
    user_param: Optional[str] = params.get("user") # Parámetro opcional 'user'
    input_type_param: Optional[str] = params.get("input_type") # Nuevo parámetro opcional para algunos modelos

    if not deployment_id: 
        return {"status": "error", "message": "Parámetro 'deployment_id' (nombre del despliegue OpenAI Embeddings) es requerido.", "http_status": 400}
    if not input_data: 
        return {"status": "error", "message": "Parámetro 'input' (string o lista de strings) es requerido.", "http_status": 400}

    url = f"{constants.AZURE_OPENAI_RESOURCE_ENDPOINT.rstrip('/')}/openai/deployments/{deployment_id}/embeddings?api-version={constants.AZURE_OPENAI_API_VERSION}"
    
    payload: Dict[str, Any] = {"input": input_data}
    if user_param: 
        payload["user"] = user_param
    if input_type_param: # Para modelos que lo soportan, ej. text-embedding-3-large
        payload["input_type"] = input_type_param
    
    log_input_type = "lista de strings" if isinstance(input_data, list) else "string"
    logger.info(f"Generando Embeddings AOAI con despliegue '{deployment_id}' para entrada tipo '{log_input_type}'.")
    logger.debug(f"Payload Embeddings: {payload}")
    
    try:
        response = client.post(
            url=url,
            scope=constants.OPENAI_SCOPE, 
            json_data=payload,
            timeout=constants.DEFAULT_API_TIMEOUT
        )
        response_data = response.json()
        return {"status": "success", "data": response_data}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        logger.error(f"Error HTTP generando Embeddings AOAI '{deployment_id}': {http_err.response.status_code if http_err.response else 'N/A'} - {error_details[:500]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {http_err.response.status_code if http_err.response else 'N/A'}", "details": error_details, "http_status": http_err.response.status_code if http_err.response else 500}
    except ValueError as val_err:
        logger.error(f"Error de Valor (auth/JSON) generando Embeddings AOAI '{deployment_id}': {val_err}", exc_info=True)
        return {"status": "error", "message": "Error de autenticación, configuración o formato de respuesta JSON.", "details": str(val_err)}
    except Exception as e:
        logger.error(f"Error inesperado generando Embeddings AOAI '{deployment_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error inesperado en Embeddings: {type(e).__name__}", "details": str(e)}

def completion(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Genera una completación de texto usando un modelo desplegado en Azure OpenAI (para modelos de tipo 'completions').
    NOTA: Azure OpenAI recomienda usar 'chat_completion' para los modelos más nuevos.
    Esta función se mantiene por compatibilidad o para modelos que solo soporten este endpoint.
    """
    if not constants.AZURE_OPENAI_RESOURCE_ENDPOINT or not constants.AZURE_OPENAI_API_VERSION:
        return {"status": "error", "message": "Configuración de Azure OpenAI incompleta (endpoint o api-version).", "http_status": 500}

    deployment_id: Optional[str] = params.get("deployment_id")
    prompt: Optional[Union[str, List[str]]] = params.get("prompt")

    if not deployment_id:
        return {"status": "error", "message": "Parámetro 'deployment_id' es requerido.", "http_status": 400}
    if not prompt:
        return {"status": "error", "message": "Parámetro 'prompt' (string o lista de strings) es requerido.", "http_status": 400}

    url = f"{constants.AZURE_OPENAI_RESOURCE_ENDPOINT.rstrip('/')}/openai/deployments/{deployment_id}/completions?api-version={constants.AZURE_OPENAI_API_VERSION}"
    
    payload: Dict[str, Any] = {"prompt": prompt}
    
    # Parámetros opcionales comunes para la API de Completions
    allowed_api_params = [
        "max_tokens", "temperature", "top_p", "frequency_penalty", 
        "presence_penalty", "stop", "logit_bias", "user", "n", 
        "logprobs", "echo", "best_of"
        # "stream" no se maneja aquí por simplicidad
    ]
    for param_key, value in params.items():
        if param_key in allowed_api_params and value is not None:
            payload[param_key] = value
            
    logger.info(f"Enviando petición de Completion a AOAI despliegue '{deployment_id}'.")
    logger.debug(f"Payload Completion (sin 'prompt'): { {k:v for k,v in payload.items() if k != 'prompt'} }")

    try:
        response = client.post(
            url=url,
            scope=constants.OPENAI_SCOPE,
            json_data=payload,
            timeout=constants.DEFAULT_API_TIMEOUT
        )
        response_data = response.json()
        return {"status": "success", "data": response_data}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        logger.error(f"Error HTTP en Completion AOAI '{deployment_id}': {http_err.response.status_code if http_err.response else 'N/A'} - {error_details[:500]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {http_err.response.status_code if http_err.response else 'N/A'}", "details": error_details, "http_status": http_err.response.status_code if http_err.response else 500}
    except ValueError as val_err:
        logger.error(f"Error de Valor (auth/JSON) en Completion AOAI '{deployment_id}': {val_err}", exc_info=True)
        return {"status": "error", "message": "Error de autenticación, configuración o formato de respuesta JSON.", "details": str(val_err)}
    except Exception as e:
        logger.error(f"Error inesperado en Completion AOAI '{deployment_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error inesperado en Completion: {type(e).__name__}", "details": str(e)}


def list_models(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lista los modelos disponibles en el recurso de Azure OpenAI.
    Esta llamada va al endpoint /openai/models del recurso, no a un despliegue específico.
    """
    if not constants.AZURE_OPENAI_RESOURCE_ENDPOINT or not constants.AZURE_OPENAI_API_VERSION:
        return {"status": "error", "message": "Configuración de Azure OpenAI incompleta (endpoint o api-version).", "http_status": 500}

    # El endpoint para listar modelos base del recurso es diferente al de los despliegues
    url = f"{constants.AZURE_OPENAI_RESOURCE_ENDPOINT.rstrip('/')}/openai/models?api-version={constants.AZURE_OPENAI_API_VERSION}"
    
    # No hay payload para esta llamada GET, 'params' se usa para control interno si fuera necesario (ej. paginación no estándar)
    # pero la API de Azure OpenAI /models no parece usar parámetros de query estándar para esta operación.
    
    logger.info(f"Listando modelos disponibles en el recurso Azure OpenAI: {constants.AZURE_OPENAI_RESOURCE_ENDPOINT}")
    
    try:
        response = client.get(
            url=url,
            scope=constants.OPENAI_SCOPE, # Mismo scope para acceder al recurso
            timeout=constants.DEFAULT_API_TIMEOUT
        )
        response_data = response.json()
        # La respuesta es una lista de objetos modelo, cada uno con 'id', 'object', 'created_at', 'owned_by', etc.
        # La clave principal de la respuesta es 'data' que contiene la lista.
        return {"status": "success", "data": response_data.get("data", [])}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        logger.error(f"Error HTTP listando modelos AOAI: {http_err.response.status_code if http_err.response else 'N/A'} - {error_details[:500]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {http_err.response.status_code if http_err.response else 'N/A'}", "details": error_details, "http_status": http_err.response.status_code if http_err.response else 500}
    except ValueError as val_err:
        logger.error(f"Error de Valor (auth/JSON) listando modelos AOAI: {val_err}", exc_info=True)
        return {"status": "error", "message": "Error de autenticación, configuración o formato de respuesta JSON.", "details": str(val_err)}
    except Exception as e:
        logger.error(f"Error inesperado listando modelos AOAI: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error inesperado listando modelos: {type(e).__name__}", "details": str(e)}

# --- FIN DEL MÓDULO actions/openai_actions.py ---