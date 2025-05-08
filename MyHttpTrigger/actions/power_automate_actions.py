# MyHttpTrigger/actions/power_automate_actions.py
import logging
import os
import requests # Para ejecutar_flow (llamada directa a trigger) y tipos de excepción
import json
from typing import Dict, Optional, Any

# Importar Credential para autenticación con Azure Management API
from azure.identity import ClientSecretCredential, CredentialUnavailableError

# Importar helper HTTP y constantes
try:
    from ..shared.helpers.http_client import hacer_llamada_api
    from ..shared.constants import (
        APP_NAME,
        AZURE_MGMT_BASE_URL,
        AZURE_MGMT_DEFAULT_SCOPE,
        LOGIC_APPS_API_VERSION,
        AZURE_MGMT_API_DEFAULT_TIMEOUT
    )
except ImportError as e:
    logging.critical(f"Error CRÍTICO importando dependencias compartidas en PowerAutomate: {e}.", exc_info=True)
    APP_NAME = "EliteDynamicsPro" # Fallback
    AZURE_MGMT_BASE_URL = "https://management.azure.com"
    AZURE_MGMT_DEFAULT_SCOPE = ["https://management.azure.com/.default"]
    LOGIC_APPS_API_VERSION = "2019-05-01"
    AZURE_MGMT_API_DEFAULT_TIMEOUT = 90
    raise ImportError(f"No se pudo importar 'hacer_llamada_api' o constantes: {e}") from e

logger = logging.getLogger(f"{APP_NAME}.actions.power_automate")

# --- Variables de Entorno Específicas para este módulo ---
# (Leídas directamente donde se usan o pasadas por parámetros)
# Se espera que AZURE_CLIENT_ID_MGMT, AZURE_CLIENT_SECRET_MGMT, AZURE_TENANT_ID,
# AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP estén configuradas.

# --- Helper de Autenticación para Azure Management API ---
_pa_credential_instance: Optional[ClientSecretCredential] = None
_pa_cached_mgmt_token: Optional[str] = None # Cache simple para el token

def _get_azure_mgmt_token(parametros: Dict[str, Any]) -> str:
    """Obtiene un token de acceso para Azure Management API usando ClientSecretCredential."""
    global _pa_credential_instance, _pa_cached_mgmt_token
    
    # Podríamos cachear el token, pero get_token de azure.identity ya lo hace.
    # Sin embargo, cachear la instancia de credencial es buena idea.

    # Leer credenciales de parámetros o variables de entorno
    # Priorizar parámetros si se quieren pasar dinámicamente, sino usar env vars.
    tenant_id = parametros.get("azure_tenant_id", os.environ.get("AZURE_TENANT_ID"))
    client_id = parametros.get("azure_client_id_mgmt", os.environ.get("AZURE_CLIENT_ID_MGMT"))
    client_secret = parametros.get("azure_client_secret_mgmt", os.environ.get("AZURE_CLIENT_SECRET_MGMT"))

    if not all([tenant_id, client_id, client_secret]):
        missing = [name for name, var in [("tenant_id",tenant_id), ("client_id_mgmt",client_id), ("client_secret_mgmt",client_secret)] if not var]
        msg = f"Faltan variables de entorno/parámetros para autenticación con Azure Management: {', '.join(missing)}"
        logger.critical(msg)
        raise ValueError(msg)

    if _pa_credential_instance is None:
        logger.info("Creando nueva instancia ClientSecretCredential para Azure Management (Power Automate).")
        try:
            _pa_credential_instance = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret
            )
        except Exception as cred_err:
            logger.critical(f"Error al crear ClientSecretCredential para Power Automate: {cred_err}", exc_info=True)
            raise Exception(f"Error configurando credencial Azure para Power Automate: {cred_err}") from cred_err
    
    try:
        logger.info(f"Solicitando token para Azure Management con scope: {AZURE_MGMT_DEFAULT_SCOPE[0]}")
        token_info = _pa_credential_instance.get_token(AZURE_MGMT_DEFAULT_SCOPE[0]) # Scope es una lista pero get_token espera string
        # _pa_cached_mgmt_token = token_info.token # Descomentar si se quiere cachear manualmente el token
        logger.info("Token para Azure Management (Power Automate) obtenido exitosamente.")
        return token_info.token
    except CredentialUnavailableError as cred_unavailable_err:
        logger.critical(f"Credencial no disponible para obtener token ARM (Power Automate): {cred_unavailable_err}", exc_info=True)
        raise Exception(f"Credencial Azure para Power Automate no disponible: {cred_unavailable_err}") from cred_unavailable_err
    except Exception as token_err:
        logger.error(f"Error inesperado obteniendo token ARM para Power Automate: {token_err}", exc_info=True)
        raise Exception(f"Error obteniendo token Azure para Power Automate: {token_err}") from token_err

def _get_arm_auth_headers(parametros_auth: Dict[str, Any]) -> Dict[str, str]:
    """Construye las cabeceras de autenticación para Azure Resource Manager (ARM) API."""
    try:
        token = _get_azure_mgmt_token(parametros_auth) # Pasar params para que tome credenciales de ahí si existen
        return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    except Exception as e:
        # No relanzar directamente, devolver error para que la función de acción lo maneje
        raise Exception(f"No se pudieron obtener cabeceras de autenticación para Azure Management API: {e}")


# ---- FUNCIONES DE ACCIÓN PARA POWER AUTOMATE (Workflows/Logic Apps) ----
# Nota: Las acciones de Power Automate a través de ARM suelen operar sobre Logic Apps Workflows.
# El token OBO de Graph (en `headers`) no se usa aquí; se usa un token de app para ARM.

def listar_flows(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Lista workflows (flujos) en una suscripción y grupo de recursos."""
    suscripcion_id = parametros.get('suscripcion_id', os.environ.get('AZURE_SUBSCRIPTION_ID'))
    grupo_recurso = parametros.get('grupo_recurso', os.environ.get('AZURE_RESOURCE_GROUP'))
    if not suscripcion_id or not grupo_recurso:
        return {"status": "error", "message": "Parámetros 'suscripcion_id' y 'grupo_recurso' (o variables de entorno) son requeridos."}

    try:
        arm_headers = _get_arm_auth_headers(parametros) # Pasar params para credenciales dinámicas
    except Exception as auth_err:
        return {"status": "error", "message": "Fallo de autenticación para Azure Management.", "details": str(auth_err)}

    url = f"{AZURE_MGMT_BASE_URL}/subscriptions/{suscripcion_id}/resourceGroups/{grupo_recurso}/providers/Microsoft.Logic/workflows?api-version={LOGIC_APPS_API_VERSION}"
    logger.info(f"Listando flujos en Suscripción '{suscripcion_id}', GrupoRecursos '{grupo_recurso}'")
    try:
        response_data = hacer_llamada_api("GET", url, arm_headers, timeout=AZURE_MGMT_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": response_data.get("value", []) if isinstance(response_data, dict) else response_data}
    except Exception as e:
        logger.error(f"Error listando flujos: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al listar flujos: {type(e).__name__}", "http_status": status_code, "details": details}

# Las demás funciones (obtener_flow, crear_flow, etc.) seguirán este patrón:
# 1. Obtener suscripcion_id, grupo_recurso, nombre_flow, etc. de `parametros` o env vars.
# 2. Obtener `arm_headers` usando `_get_arm_auth_headers(parametros)`.
# 3. Construir la URL específica de ARM.
# 4. Llamar a `hacer_llamada_api` con el método, URL, `arm_headers`, y `json_data` si es POST/PUT/PATCH.
# 5. Manejar la respuesta y errores.

def obtener_flow(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    nombre_flow: Optional[str] = parametros.get("nombre_flow")
    if not nombre_flow: return {"status": "error", "message": "'nombre_flow' es requerido."}
    
    suscripcion_id = parametros.get('suscripcion_id', os.environ.get('AZURE_SUBSCRIPTION_ID'))
    grupo_recurso = parametros.get('grupo_recurso', os.environ.get('AZURE_RESOURCE_GROUP'))
    if not suscripcion_id or not grupo_recurso:
        return {"status": "error", "message": "Parámetros 'suscripcion_id' y 'grupo_recurso' (o env vars) requeridos."}

    try: arm_headers = _get_arm_auth_headers(parametros)
    except Exception as auth_err: return {"status": "error", "message": "Fallo de autenticación ARM.", "details": str(auth_err)}

    url = f"{AZURE_MGMT_BASE_URL}/subscriptions/{suscripcion_id}/resourceGroups/{grupo_recurso}/providers/Microsoft.Logic/workflows/{nombre_flow}?api-version={LOGIC_APPS_API_VERSION}"
    logger.info(f"Obteniendo flow '{nombre_flow}' en RG '{grupo_recurso}'")
    try:
        flow_data = hacer_llamada_api("GET", url, arm_headers, timeout=AZURE_MGMT_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": flow_data}
    except Exception as e:
        logger.error(f"Error obteniendo flow '{nombre_flow}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            if status_code == 404: return {"status": "error", "message": f"Flow '{nombre_flow}' no encontrado.", "details": details}
        return {"status": "error", "message": f"Error al obtener flow: {type(e).__name__}", "http_status": status_code, "details": details}


def ejecutar_flow(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Ejecuta un flujo de Power Automate que tiene un trigger HTTP.
    La URL del trigger y cualquier autenticación específica del trigger deben ser proporcionadas.
    Los 'headers' pasados a esta función se usarán para llamar al trigger del flow.
    """
    flow_trigger_url: Optional[str] = parametros.get("flow_trigger_url")
    payload: Optional[Dict[str, Any]] = parametros.get("payload") # Payload para el trigger HTTP

    if not flow_trigger_url:
        return {"status": "error", "message": "Parámetro 'flow_trigger_url' (URL del trigger HTTP del flujo) es requerido."}

    # Usar las cabeceras pasadas a la función de acción, ya que pueden contener
    # autenticación específica para el trigger del flujo (ej. API key, o el token OBO si el flujo lo espera).
    # Quitar 'Content-Type' si vamos a enviar JSON, requests lo añade.
    request_headers = headers.copy()
    # Si hay payload y el Content-Type no está seteado, requests.post con json=payload lo seteará a application/json
    # Si el payload es diferente, el Content-Type debe venir en los headers o ser seteado aquí.
    if payload and 'Content-Type' not in request_headers:
        request_headers['Content-Type'] = 'application/json'
        
    logger.info(f"Ejecutando trigger de Power Automate flow: POST {flow_trigger_url}")
    try:
        # Usar requests.post directamente aquí es más flexible para triggers HTTP variados.
        # El helper hacer_llamada_api está más orientado a Graph API.
        # Timeout largo por si el flujo tarda.
        response = requests.post(flow_trigger_url, headers=request_headers, json=payload if payload and request_headers.get('Content-Type') == 'application/json' else None, data=payload if payload and request_headers.get('Content-Type') != 'application/json' else None, timeout=max(AZURE_MGMT_API_DEFAULT_TIMEOUT, 120))
        response.raise_for_status() # Lanza error para 4xx/5xx
        
        logger.info(f"Trigger de flow '{flow_trigger_url}' invocado. Status: {response.status_code}")
        
        # Intentar parsear JSON, si no, devolver texto.
        try: response_body = response.json()
        except json.JSONDecodeError: response_body = response.text
        
        # Un 202 Accepted es común para triggers de flujo.
        if response.status_code == 202:
            return {"status": "success", "message": "Flujo invocado, ejecución en progreso (202 Accepted).", "status_code": response.status_code, "response_headers": dict(response.headers), "response_body": response_body}
        else:
            return {"status": "success" if response.ok else "error", "message": f"Respuesta del trigger del flujo: {response.reason}", "status_code": response.status_code, "response_body": response_body}

    except requests.exceptions.RequestException as e:
        error_body = e.response.text[:500] if e.response is not None else "N/A"
        logger.error(f"Error Request ejecutando trigger de flow '{flow_trigger_url}': {e}. Respuesta: {error_body}", exc_info=True)
        return {"status": "error", "message": f"Error API ejecutando trigger de flow: {type(e).__name__}", "details": str(e)}
    except Exception as e:
        logger.error(f"Error inesperado ejecutando trigger de flow '{flow_trigger_url}': {e}", exc_info=True)
        return {"status": "error", "message": f"Error inesperado al ejecutar trigger de flow: {type(e).__name__}", "details": str(e)}


def obtener_estado_ejecucion_flow(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    nombre_flow: Optional[str] = parametros.get("nombre_flow")
    run_id: Optional[str] = parametros.get("run_id")
    if not nombre_flow or not run_id:
        return {"status": "error", "message": "Parámetros 'nombre_flow' y 'run_id' son requeridos."}

    suscripcion_id = parametros.get('suscripcion_id', os.environ.get('AZURE_SUBSCRIPTION_ID'))
    grupo_recurso = parametros.get('grupo_recurso', os.environ.get('AZURE_RESOURCE_GROUP'))
    if not suscripcion_id or not grupo_recurso:
        return {"status": "error", "message": "Parámetros 'suscripcion_id' y 'grupo_recurso' (o env vars) requeridos."}

    try: arm_headers = _get_arm_auth_headers(parametros)
    except Exception as auth_err: return {"status": "error", "message": "Fallo de autenticación ARM.", "details": str(auth_err)}

    url = f"{AZURE_MGMT_BASE_URL}/subscriptions/{suscripcion_id}/resourceGroups/{grupo_recurso}/providers/Microsoft.Logic/workflows/{nombre_flow}/runs/{run_id}?api-version={LOGIC_APPS_API_VERSION}"
    logger.info(f"Obteniendo estado de ejecución '{run_id}' del flow '{nombre_flow}'")
    try:
        run_data = hacer_llamada_api("GET", url, arm_headers, timeout=AZURE_MGMT_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": run_data}
    except Exception as e:
        logger.error(f"Error obteniendo estado de ejecución '{run_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al obtener estado de ejecución: {type(e).__name__}", "http_status": status_code, "details": details}

# Las funciones crear_flow, actualizar_flow, eliminar_flow necesitarían el cuerpo de definición del flujo (JSON grande).
# Por ahora, las dejo como stubs o con la lógica de tu ejemplo, pero requerirían que `definicion_flow`
# sea un parámetro bien formado.

# --- FIN DEL MÓDULO actions/power_automate_actions.py ---