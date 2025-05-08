# MyHttpTrigger/actions/power_bi_actions.py
import logging
import requests # Solo para tipos de excepción
import json
import os
from typing import Dict, List, Optional, Any

# Importar Credential para autenticación de aplicación con Power BI API
from azure.identity import ClientSecretCredential, CredentialUnavailableError

# Importar helper HTTP y constantes (principalmente para logging y timeout base)
try:
    from ..shared.helpers.http_client import hacer_llamada_api
    from ..shared.constants import APP_NAME, GRAPH_API_DEFAULT_TIMEOUT # Usar timeout como base
except ImportError as e:
    logging.critical(f"Error CRÍTICO importando dependencias compartidas en PowerBI: {e}.", exc_info=True)
    APP_NAME = "EliteDynamicsPro" # Fallback
    GRAPH_API_DEFAULT_TIMEOUT = 90 # Usar un timeout más largo para PBI
    # No se puede continuar sin el helper si la importación falla
    raise ImportError(f"No se pudo importar 'hacer_llamada_api' o constantes: {e}") from e

logger = logging.getLogger(f"{APP_NAME}.actions.power_bi")

# --- Constantes y Configuración Específica para Power BI API ---
PBI_API_BASE_URL = "https://api.powerbi.com/v1.0/myorg" # Endpoint común 'myorg'
# Scope específico para la API REST de Power BI
PBI_API_DEFAULT_SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]
# Timeout para llamadas a Power BI API
PBI_API_TIMEOUT = max(GRAPH_API_DEFAULT_TIMEOUT, 90) # Permitir más tiempo

# --- Helper de Autenticación (Específico para Power BI API con Client Credentials) ---
_pbi_credential_instance: Optional[ClientSecretCredential] = None

def _get_powerbi_api_token(parametros: Dict[str, Any]) -> str:
    """Obtiene un token de acceso para Power BI API usando Client Credentials."""
    global _pbi_credential_instance
    
    # Leer credenciales de parámetros o variables de entorno específicas de PBI
    # Estos DEBEN estar configurados en local.settings.json o App Settings
    tenant_id = parametros.get("pbi_tenant_id", os.environ.get("PBI_TENANT_ID", os.environ.get("TENANT_ID"))) # Reutilizar TENANT_ID si no hay PBI_TENANT_ID
    client_id = parametros.get("pbi_client_id", os.environ.get("PBI_CLIENT_ID"))
    client_secret = parametros.get("pbi_client_secret", os.environ.get("PBI_CLIENT_SECRET"))

    if not all([tenant_id, client_id, client_secret]):
        missing = [name for name, var in [("PBI_TENANT_ID",tenant_id), ("PBI_CLIENT_ID",client_id), ("PBI_CLIENT_SECRET",client_secret)] if not var]
        msg = f"Faltan variables de entorno/parámetros para autenticación con Power BI API: {', '.join(missing)}"
        logger.critical(msg)
        raise ValueError(msg)

    if _pbi_credential_instance is None:
        logger.info("Creando nueva instancia ClientSecretCredential para Power BI API.")
        try:
            _pbi_credential_instance = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret
            )
        except Exception as cred_err:
            logger.critical(f"Error al crear ClientSecretCredential para Power BI: {cred_err}", exc_info=True)
            raise Exception(f"Error configurando credencial para Power BI: {cred_err}") from cred_err
    
    try:
        logger.info(f"Solicitando token para Power BI API con scope: {PBI_API_DEFAULT_SCOPE[0]}")
        token_info = _pbi_credential_instance.get_token(PBI_API_DEFAULT_SCOPE[0])
        logger.info("Token para Power BI API obtenido exitosamente.")
        return token_info.token
    except CredentialUnavailableError as cred_unavailable_err:
        logger.critical(f"Credencial no disponible para obtener token Power BI: {cred_unavailable_err}", exc_info=True)
        raise Exception(f"Credencial para Power BI no disponible: {cred_unavailable_err}") from cred_unavailable_err
    except Exception as token_err:
        logger.error(f"Error inesperado obteniendo token Power BI: {token_err}", exc_info=True)
        raise Exception(f"Error obteniendo token para Power BI: {token_err}") from token_err

def _get_pbi_auth_headers(parametros_auth: Dict[str, Any]) -> Dict[str, str]:
    """Construye las cabeceras de autenticación para Power BI API."""
    try:
        token = _get_powerbi_api_token(parametros_auth)
        return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    except Exception as e:
        raise Exception(f"No se pudieron obtener cabeceras auth para Power BI API: {e}") from e

# ---- FUNCIONES DE ACCIÓN PARA POWER BI ----
# Nota: El parámetro 'headers' recibido por estas funciones (con el token OBO de Graph)
# NO se utiliza directamente, ya que usamos un token de aplicación específico para Power BI.

def listar_workspaces(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Lista los workspaces (grupos) de Power BI en la organización."""
    # Parámetros opcionales de la API de PBI: $top, $skip, $filter
    top: Optional[int] = parametros.get("top")
    filter_query: Optional[str] = parametros.get("filter")
    
    try:
        pbi_headers = _get_pbi_auth_headers(parametros)
    except Exception as auth_err:
        return {"status": "error", "message": "Fallo de autenticación para Power BI API.", "details": str(auth_err)}

    url = f"{PBI_API_BASE_URL}/groups" # Endpoint para listar workspaces (grupos)
    params_query: Dict[str, Any] = {}
    if top: params_query['$top'] = top
    if filter_query: params_query['$filter'] = filter_query
    
    logger.info(f"Listando workspaces de Power BI (Top: {top or 'all'}, Filter: {filter_query or 'none'})")
    try:
        # Nota: La paginación completa necesitaría manejar la respuesta si PBI la usa.
        response_data = hacer_llamada_api("GET", url, pbi_headers, params=params_query or None, timeout=PBI_API_TIMEOUT)
        return {"status": "success", "data": response_data.get("value", []) if isinstance(response_data, dict) else response_data}
    except Exception as e:
        logger.error(f"Error listando workspaces Power BI: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al listar workspaces Power BI: {type(e).__name__}", "http_status": status_code, "details": details}

def listar_datasets(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Lista datasets en 'my workspace' o en un workspace específico."""
    workspace_id: Optional[str] = parametros.get("workspace_id") # ID del workspace (grupo)

    try: pbi_headers = _get_pbi_auth_headers(parametros)
    except Exception as auth_err: return {"status": "error", "message": "Fallo de autenticación PBI.", "details": str(auth_err)}

    if workspace_id:
        url = f"{PBI_API_BASE_URL}/groups/{workspace_id}/datasets"
        log_owner = f"workspace '{workspace_id}'"
    else: # Listar datasets en "My Workspace"
        url = f"{PBI_API_BASE_URL}/datasets"
        log_owner = "My Workspace"

    logger.info(f"Listando datasets Power BI en {log_owner}")
    try:
        response_data = hacer_llamada_api("GET", url, pbi_headers, timeout=PBI_API_TIMEOUT)
        return {"status": "success", "data": response_data.get("value", []) if isinstance(response_data, dict) else response_data}
    except Exception as e:
        logger.error(f"Error listando datasets Power BI en {log_owner}: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al listar datasets PBI: {type(e).__name__}", "http_status": status_code, "details": details}

def refrescar_dataset(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Inicia un refresco de datos para un dataset específico."""
    dataset_id: Optional[str] = parametros.get("dataset_id")
    workspace_id: Optional[str] = parametros.get("workspace_id") # Opcional si el dataset está en "My Workspace"
    notify_option: str = parametros.get("notify_option", "MailOnCompletion") # O NoNotification, MailOnFailure

    if not dataset_id: return {"status": "error", "message": "Parámetro 'dataset_id' es requerido."}

    try: pbi_headers = _get_pbi_auth_headers(parametros)
    except Exception as auth_err: return {"status": "error", "message": "Fallo de autenticación PBI.", "details": str(auth_err)}

    if workspace_id:
        url = f"{PBI_API_BASE_URL}/groups/{workspace_id}/datasets/{dataset_id}/refreshes"
        log_owner = f"workspace '{workspace_id}'"
    else:
        url = f"{PBI_API_BASE_URL}/datasets/{dataset_id}/refreshes"
        log_owner = "My Workspace"
        
    # Body opcional para notificaciones
    body = {"notifyOption": notify_option} if notify_option else None
    
    logger.info(f"Iniciando refresco para dataset PBI '{dataset_id}' en {log_owner}")
    try:
        # POST a /refreshes devuelve 202 Accepted si se inicia el refresco
        response_obj = hacer_llamada_api("POST", url, pbi_headers, json_data=body, timeout=PBI_API_TIMEOUT, expect_json=False)
        
        if isinstance(response_obj, requests.Response) and response_obj.status_code == 202:
            request_id_pbi = response_obj.headers.get("RequestId")
            logger.info(f"Solicitud de refresco aceptada (202). RequestId: {request_id_pbi}")
            return {"status": "success", "message": "Refresco de dataset iniciado.", "dataset_id": dataset_id, "pbi_request_id": request_id_pbi}
        else:
             status_code = response_obj.status_code if isinstance(response_obj, requests.Response) else 500
             details = response_obj.text[:200] if isinstance(response_obj, requests.Response) else f"Tipo inesperado: {type(response_obj)}"
             logger.error(f"Respuesta inesperada al iniciar refresco PBI: {status_code}. Detalles: {details}")
             return {"status": "error", "message": f"Respuesta inesperada {status_code} al iniciar refresco.", "details": details}
    except Exception as e:
        logger.error(f"Error refrescando dataset PBI '{dataset_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al iniciar refresco de dataset PBI: {type(e).__name__}", "http_status": status_code, "details": details}

def obtener_estado_refresco_dataset(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Obtiene el historial de refrescos (el último por defecto) para un dataset."""
    dataset_id: Optional[str] = parametros.get("dataset_id")
    workspace_id: Optional[str] = parametros.get("workspace_id")
    top: int = int(parametros.get("top", 1)) # Por defecto, obtener solo el último estado

    if not dataset_id: return {"status": "error", "message": "Parámetro 'dataset_id' es requerido."}

    try: pbi_headers = _get_pbi_auth_headers(parametros)
    except Exception as auth_err: return {"status": "error", "message": "Fallo de autenticación PBI.", "details": str(auth_err)}

    if workspace_id:
        url = f"{PBI_API_BASE_URL}/groups/{workspace_id}/datasets/{dataset_id}/refreshes"
        log_owner = f"workspace '{workspace_id}'"
    else:
        url = f"{PBI_API_BASE_URL}/datasets/{dataset_id}/refreshes"
        log_owner = "My Workspace"
        
    params_query = {'$top': top}
    
    logger.info(f"Obteniendo estado de refresco(s) para dataset PBI '{dataset_id}' en {log_owner} (Top: {top})")
    try:
        response_data = hacer_llamada_api("GET", url, pbi_headers, params=params_query, timeout=PBI_API_TIMEOUT)
        return {"status": "success", "data": response_data.get("value", []) if isinstance(response_data, dict) else response_data}
    except Exception as e:
        logger.error(f"Error obteniendo estado refresco PBI '{dataset_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al obtener estado de refresco PBI: {type(e).__name__}", "http_status": status_code, "details": details}


def listar_reports(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Lista reports en 'my workspace' o en un workspace específico."""
    workspace_id: Optional[str] = parametros.get("workspace_id")

    try: pbi_headers = _get_pbi_auth_headers(parametros)
    except Exception as auth_err: return {"status": "error", "message": "Fallo de autenticación PBI.", "details": str(auth_err)}

    if workspace_id:
        url = f"{PBI_API_BASE_URL}/groups/{workspace_id}/reports"
        log_owner = f"workspace '{workspace_id}'"
    else:
        url = f"{PBI_API_BASE_URL}/reports"
        log_owner = "My Workspace"

    logger.info(f"Listando reports Power BI en {log_owner}")
    try:
        # La paginación podría aplicar aquí también
        response_data = hacer_llamada_api("GET", url, pbi_headers, timeout=PBI_API_TIMEOUT)
        return {"status": "success", "data": response_data.get("value", []) if isinstance(response_data, dict) else response_data}
    except Exception as e:
        logger.error(f"Error listando reports Power BI en {log_owner}: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al listar reports PBI: {type(e).__name__}", "http_status": status_code, "details": details}


# --- FIN DEL MÓDULO actions/power_bi_actions.py ---