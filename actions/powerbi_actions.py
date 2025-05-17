# MyHttpTrigger/actions/power_bi_actions.py
import logging
import requests # Usaremos requests directamente para la API de Power BI
import json
import os
import time # Para la espera en export_report
from typing import Dict, List, Optional, Any

# Importar Credential para autenticación de aplicación con Power BI API
from azure.identity import ClientSecretCredential, CredentialUnavailableError

# Importar constantes compartidas (principalmente para logging y timeout base si es necesario)
from shared import constants # APP_NAME (si se usa), DEFAULT_API_TIMEOUT

# Logger específico para este módulo
logger = logging.getLogger(__name__) # Usar __name__ para el logger es una buena práctica

# --- Constantes y Configuración Específica para Power BI API ---
PBI_API_BASE_URL_MYORG = "https://api.powerbi.com/v1.0/myorg" # Endpoint común 'myorg'
# Scope específico para la API REST de Power BI
PBI_API_DEFAULT_SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]
# Timeout para llamadas a Power BI API (puede ser más largo que el default de Graph)
PBI_API_CALL_TIMEOUT = max(constants.DEFAULT_API_TIMEOUT, 120) # Ej. 120 segundos

# --- Helper de Autenticación (Específico para Power BI API con Client Credentials) ---
_pbi_credential_instance: Optional[ClientSecretCredential] = None
_pbi_last_token_info: Optional[Dict[str, Any]] = None # Cache simple para el token y su expiración

def _get_powerbi_api_token(parametros_auth_override: Optional[Dict[str, Any]] = None) -> str:
    """
    Obtiene un token de acceso para Power BI API usando Client Credentials.
    Permite anular credenciales de entorno con `parametros_auth_override`.
    """
    global _pbi_credential_instance, _pbi_last_token_info

    # Si tenemos un token y no ha expirado (con un margen), lo reutilizamos.
    # Nota: get_token de azure-identity ya hace caching, pero esto es un ejemplo de cache manual si se necesitara.
    # Por simplicidad, confiaremos en el cache de azure-identity y obtendremos uno nuevo si es necesario.

    # Leer credenciales de parámetros o variables de entorno específicas de PBI
    # `parametros_auth_override` permite pasar credenciales dinámicamente (ej. para multi-tenant scenarios no comunes aquí)
    auth_params = parametros_auth_override or {}
    
    tenant_id = auth_params.get("pbi_tenant_id", os.environ.get("PBI_TENANT_ID", os.environ.get("TENANT_ID")))
    client_id = auth_params.get("pbi_client_id", os.environ.get("PBI_CLIENT_ID"))
    client_secret = auth_params.get("pbi_client_secret", os.environ.get("PBI_CLIENT_SECRET"))

    if not all([tenant_id, client_id, client_secret]):
        missing = [name for name, var in [("PBI_TENANT_ID/TENANT_ID", tenant_id), 
                                          ("PBI_CLIENT_ID", client_id), 
                                          ("PBI_CLIENT_SECRET", client_secret)] if not var]
        msg = f"Faltan variables de entorno/parámetros para autenticación con Power BI API: {', '.join(missing)}"
        logger.critical(msg)
        raise ValueError(msg)

    # Recrear la instancia de credencial si los IDs han cambiado (improbable en este flujo pero robusto)
    # O si no existe. Azure Identity maneja el cacheo del token internamente.
    if _pbi_credential_instance is None or \
       (_pbi_credential_instance._tenant_id != tenant_id or _pbi_credential_instance._client_id != client_id):
        logger.info("Creando/Recreando instancia ClientSecretCredential para Power BI API.")
        try:
            _pbi_credential_instance = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret
            )
        except Exception as cred_err:
            logger.critical(f"Error al crear ClientSecretCredential para Power BI: {cred_err}", exc_info=True)
            raise ConnectionError(f"Error configurando credencial para Power BI: {cred_err}") from cred_err
    
    try:
        logger.info(f"Solicitando token para Power BI API con scope: {PBI_API_DEFAULT_SCOPE[0]}")
        token_credential = _pbi_credential_instance.get_token(PBI_API_DEFAULT_SCOPE[0])
        logger.info("Token para Power BI API obtenido exitosamente.")
        # _pbi_last_token_info = {"token": token_credential.token, "expires_on": token_credential.expires_on}
        return token_credential.token
    except CredentialUnavailableError as cred_unavailable_err:
        logger.critical(f"Credencial no disponible para obtener token Power BI: {cred_unavailable_err}", exc_info=True)
        raise ConnectionAbortedError(f"Credencial para Power BI no disponible: {cred_unavailable_err}") from cred_unavailable_err
    except Exception as token_err: # Captura errores más genéricos de get_token
        logger.error(f"Error inesperado obteniendo token Power BI: {token_err}", exc_info=True)
        # Podría ser un problema de configuración de la App Reg, permisos, etc.
        raise ConnectionRefusedError(f"Error obteniendo token para Power BI: {token_err}") from token_err

def _get_pbi_auth_headers(parametros_auth_override: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Construye las cabeceras de autenticación para Power BI API."""
    try:
        token = _get_powerbi_api_token(parametros_auth_override)
        return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    except Exception as e: # Captura ValueError, ConnectionError, etc. de _get_powerbi_api_token
        # Este error se propagará y será manejado por la función de acción.
        raise e

# ---- FUNCIONES DE ACCIÓN PARA POWER BI ----
# Nota: El parámetro 'client: AuthenticatedHttpClient' recibido por estas funciones
# (debido al patrón del ejecutor) NO se utiliza directamente aquí, ya que usamos un 
# token de aplicación específico para Power BI obtenido vía ClientSecretCredential.

def listar_workspaces(client: Optional[AuthenticatedHttpClient], params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista los workspaces (grupos) de Power BI a los que la App tiene acceso."""
    # El parámetro 'client' se ignora. Se usa autenticación de app específica para PBI.
    
    api_query_params: Dict[str, Any] = {}
    if params.get("top"): api_query_params['$top'] = min(int(params["top"]), 100) # Max top es 100 para groups
    if params.get("skip"): api_query_params['$skip'] = int(params["skip"])
    if params.get("filter"): api_query_params['$filter'] = params["filter"]
    
    try:
        pbi_headers = _get_pbi_auth_headers(params.get("auth_override"))
    except Exception as auth_err:
        return {"status": "error", "message": "Fallo de autenticación para Power BI API.", "details": str(auth_err), "http_status": 401}

    url = f"{PBI_API_BASE_URL_MYORG}/groups" # Endpoint para listar workspaces (grupos)
    
    logger.info(f"Listando workspaces de Power BI con params: {api_query_params}")
    try:
        response = requests.get(url, headers=pbi_headers, params=api_query_params or None, timeout=PBI_API_CALL_TIMEOUT)
        response.raise_for_status() # Lanza HTTPError para 4xx/5xx
        response_data = response.json()
        return {"status": "success", "data": response_data.get("value", [])}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code
        logger.error(f"Error HTTP listando workspaces Power BI: {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e: # Otros errores (ej. JSONDecodeError, Timeout)
        logger.error(f"Error listando workspaces Power BI: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al listar workspaces Power BI: {type(e).__name__}", "details": str(e), "http_status": 500}

def list_datasets(client: Optional[AuthenticatedHttpClient], params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista datasets en 'my workspace' (si no se da workspace_id) o en un workspace específico."""
    # El parámetro 'client' se ignora.
    workspace_id: Optional[str] = params.get("workspace_id") 

    try: 
        pbi_headers = _get_pbi_auth_headers(params.get("auth_override"))
    except Exception as auth_err: 
        return {"status": "error", "message": "Fallo de autenticación PBI.", "details": str(auth_err), "http_status": 401}

    log_owner: str
    if workspace_id:
        url = f"{PBI_API_BASE_URL_MYORG}/groups/{workspace_id}/datasets"
        log_owner = f"workspace '{workspace_id}'"
    else: # Listar datasets en "My Workspace" (del usuario efectivo de la App Reg, o si tiene acceso)
          # Para App-Only, '/datasets' bajo /myorg podría no ser lo esperado.
          # Usualmente se opera dentro de un group_id. Si se quiere "My Workspace" de un usuario específico, es más complejo.
          # Por ahora, asumimos que si no hay workspace_id, se refiere a los datasets del 'myorg' a los que la app tiene acceso,
          # lo cual podría ser una lista vacía si la app no tiene datasets directos fuera de workspaces.
          # O el usuario pretende listar los de su propio "My Workspace" (no directamente posible con app-only puro sin delegación).
          # Para ser más claro, esta función se enfoca en datasets dentro de un workspace o todos los accesibles.
        url = f"{PBI_API_BASE_URL_MYORG}/datasets" # Lista datasets a los que la App tiene acceso en la org.
        log_owner = "la organización (accesibles por la App)"
        if not workspace_id:
             logger.warning("Listando datasets a nivel de organización sin workspace_id. El resultado depende de los permisos de la App.")


    logger.info(f"Listando datasets Power BI en {log_owner}")
    try:
        response = requests.get(url, headers=pbi_headers, timeout=PBI_API_CALL_TIMEOUT)
        response.raise_for_status()
        response_data = response.json()
        return {"status": "success", "data": response_data.get("value", [])}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code
        logger.error(f"Error HTTP listando datasets PBI en {log_owner}: {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error listando datasets PBI en {log_owner}: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al listar datasets PBI: {type(e).__name__}", "details": str(e), "http_status": 500}

def refresh_dataset(client: Optional[AuthenticatedHttpClient], params: Dict[str, Any]) -> Dict[str, Any]:
    """Inicia un refresco de datos para un dataset específico."""
    # El parámetro 'client' se ignora.
    dataset_id: Optional[str] = params.get("dataset_id")
    workspace_id: Optional[str] = params.get("workspace_id") # Opcional si el dataset está en "My Workspace" (ver nota en list_datasets)
    notify_option: str = params.get("notify_option", "MailOnCompletion") # O NoNotification, MailOnFailure

    if not dataset_id: 
        return {"status": "error", "message": "Parámetro 'dataset_id' es requerido.", "http_status": 400}

    try: 
        pbi_headers = _get_pbi_auth_headers(params.get("auth_override"))
    except Exception as auth_err: 
        return {"status": "error", "message": "Fallo de autenticación PBI.", "details": str(auth_err), "http_status": 401}

    log_owner: str
    if workspace_id:
        url = f"{PBI_API_BASE_URL_MYORG}/groups/{workspace_id}/datasets/{dataset_id}/refreshes"
        log_owner = f"workspace '{workspace_id}'"
    else:
        url = f"{PBI_API_BASE_URL_MYORG}/datasets/{dataset_id}/refreshes"
        log_owner = "dataset a nivel de organización (verificar acceso de App)"
        logger.warning(f"Iniciando refresco para dataset '{dataset_id}' sin workspace_id. El contexto es a nivel de organización.")
        
    # Body opcional para notificaciones
    # https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/refresh-dataset#request-body
    # Valores para notifyOption: "MailOnCompletion", "MailOnFailure", "NoNotification"
    payload = {"notifyOption": notify_option} if notify_option in ["MailOnCompletion", "MailOnFailure", "NoNotification"] else {}
    
    logger.info(f"Iniciando refresco para dataset PBI '{dataset_id}' en {log_owner} con Notify: {notify_option}")
    try:
        response = requests.post(url, headers=pbi_headers, json=payload, timeout=PBI_API_CALL_TIMEOUT)
        # POST a /refreshes devuelve 202 Accepted si se inicia el refresco y no hay otro en curso.
        # Si ya hay un refresco en curso para ese dataset, puede devolver 400 o 409.
        if response.status_code == 202:
            request_id_pbi = response.headers.get("RequestId") # ID de la solicitud de refresco
            logger.info(f"Solicitud de refresco para dataset '{dataset_id}' aceptada (202). PBI RequestId: {request_id_pbi}")
            return {"status": "success", "message": "Refresco de dataset iniciado.", "dataset_id": dataset_id, "pbi_request_id": request_id_pbi, "http_status": 202}
        else:
            # Manejar otros códigos de estado si la API los devuelve de forma estructurada.
            response.raise_for_status() # Dejar que esto lance error para otros casos no 202
            # Si no lanza error pero no es 202, es un caso inesperado
            return {"status": "warning", "message": f"Respuesta inesperada {response.status_code} al iniciar refresco.", "details": response.text, "http_status": response.status_code}

    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code
        logger.error(f"Error HTTP refrescando dataset PBI '{dataset_id}': {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP al iniciar refresco: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error refrescando dataset PBI '{dataset_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al iniciar refresco de dataset PBI: {type(e).__name__}", "details": str(e), "http_status": 500}

def obtener_estado_refresco_dataset(client: Optional[AuthenticatedHttpClient], params: Dict[str, Any]) -> Dict[str, Any]:
    """Obtiene el historial de refrescos (el último por defecto) para un dataset."""
    # El parámetro 'client' se ignora.
    dataset_id: Optional[str] = params.get("dataset_id")
    workspace_id: Optional[str] = params.get("workspace_id")
    top: int = int(params.get("top", 1)) # Por defecto, obtener solo el último estado de refresco

    if not dataset_id: 
        return {"status": "error", "message": "Parámetro 'dataset_id' es requerido.", "http_status": 400}

    try: 
        pbi_headers = _get_pbi_auth_headers(params.get("auth_override"))
    except Exception as auth_err: 
        return {"status": "error", "message": "Fallo de autenticación PBI.", "details": str(auth_err), "http_status": 401}

    log_owner: str
    if workspace_id:
        url = f"{PBI_API_BASE_URL_MYORG}/groups/{workspace_id}/datasets/{dataset_id}/refreshes"
        log_owner = f"workspace '{workspace_id}'"
    else:
        url = f"{PBI_API_BASE_URL_MYORG}/datasets/{dataset_id}/refreshes"
        log_owner = "dataset a nivel de organización"
        
    api_query_params = {'$top': top}
    
    logger.info(f"Obteniendo estado de refresco(s) para dataset PBI '{dataset_id}' en {log_owner} (Top: {top})")
    try:
        response = requests.get(url, headers=pbi_headers, params=api_query_params, timeout=PBI_API_CALL_TIMEOUT)
        response.raise_for_status()
        response_data = response.json()
        return {"status": "success", "data": response_data.get("value", [])}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code
        logger.error(f"Error HTTP obteniendo estado refresco PBI '{dataset_id}': {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error obteniendo estado refresco PBI '{dataset_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al obtener estado de refresco PBI: {type(e).__name__}", "details": str(e), "http_status": 500}

def list_reports(client: Optional[AuthenticatedHttpClient], params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista reports en 'my workspace' o en un workspace específico."""
    # El parámetro 'client' se ignora.
    workspace_id: Optional[str] = params.get("workspace_id")

    try: 
        pbi_headers = _get_pbi_auth_headers(params.get("auth_override"))
    except Exception as auth_err: 
        return {"status": "error", "message": "Fallo de autenticación PBI.", "details": str(auth_err), "http_status": 401}
    
    log_owner: str
    if workspace_id:
        url = f"{PBI_API_BASE_URL_MYORG}/groups/{workspace_id}/reports"
        log_owner = f"workspace '{workspace_id}'"
    else:
        url = f"{PBI_API_BASE_URL_MYORG}/reports"
        log_owner = "la organización (accesibles por la App)"
        if not workspace_id:
             logger.warning("Listando reports a nivel de organización sin workspace_id. El resultado depende de los permisos de la App.")


    logger.info(f"Listando reports Power BI en {log_owner}")
    try:
        response = requests.get(url, headers=pbi_headers, timeout=PBI_API_CALL_TIMEOUT)
        response.raise_for_status()
        response_data = response.json()
        return {"status": "success", "data": response_data.get("value", [])}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code
        logger.error(f"Error HTTP listando reports PBI en {log_owner}: {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error listando reports PBI en {log_owner}: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al listar reports PBI: {type(e).__name__}", "details": str(e), "http_status": 500}

def list_dashboards(client: Optional[AuthenticatedHttpClient], params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista dashboards en un workspace específico o en 'my org' (accesibles por la App)."""
    # El parámetro 'client' se ignora.
    workspace_id: Optional[str] = params.get("workspace_id")

    try:
        pbi_headers = _get_pbi_auth_headers(params.get("auth_override"))
    except Exception as auth_err:
        return {"status": "error", "message": "Fallo de autenticación PBI.", "details": str(auth_err), "http_status": 401}

    log_owner: str
    if workspace_id:
        url = f"{PBI_API_BASE_URL_MYORG}/groups/{workspace_id}/dashboards"
        log_owner = f"workspace '{workspace_id}'"
    else:
        url = f"{PBI_API_BASE_URL_MYORG}/dashboards" # Dashboards a nivel de organización accesibles por la app
        log_owner = "la organización (accesibles por la App)"
        logger.warning("Listando dashboards a nivel de organización sin workspace_id.")
        
    logger.info(f"Listando dashboards Power BI en {log_owner}")
    try:
        response = requests.get(url, headers=pbi_headers, timeout=PBI_API_CALL_TIMEOUT)
        response.raise_for_status()
        response_data = response.json()
        return {"status": "success", "data": response_data.get("value", [])}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code
        logger.error(f"Error HTTP listando dashboards PBI en {log_owner}: {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error listando dashboards PBI en {log_owner}: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al listar dashboards PBI: {type(e).__name__}", "details": str(e), "http_status": 500}

def export_report(client: Optional[AuthenticatedHttpClient], params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inicia la exportación de un informe de Power BI a un archivo (PDF, PPTX, PNG).
    Esta es una operación asíncrona. Esta función inicia la exportación y devuelve el ID de la exportación.
    Se necesitaría otra función para verificar el estado y descargar el archivo.
    """
    # El parámetro 'client' se ignora.
    report_id: Optional[str] = params.get("report_id")
    workspace_id: Optional[str] = params.get("workspace_id") # Requerido si el informe no está en "My Workspace"
    export_format: str = params.get("format", "PDF").upper() # PDF, PPTX, PNG
    # Otros parámetros opcionales: powerBIReportConfiguration, datasetRefresh, etc.
    # Ver: https://learn.microsoft.com/en-us/rest/api/power-bi/reports/export-to-file-in-group
    report_level_filters: Optional[List[Dict[str, Any]]] = params.get("report_level_filters") # ej: [{"filter": "Region eq 'West'"}]
    page_name: Optional[str] = params.get("page_name") # Para exportar una página específica

    if not report_id:
        return {"status": "error", "message": "Parámetro 'report_id' es requerido.", "http_status": 400}
    if export_format not in ["PDF", "PPTX", "PNG"]:
        return {"status": "error", "message": "Parámetro 'format' debe ser PDF, PPTX, o PNG.", "http_status": 400}

    try:
        pbi_headers = _get_pbi_auth_headers(params.get("auth_override"))
    except Exception as auth_err:
        return {"status": "error", "message": "Fallo de autenticación PBI.", "details": str(auth_err), "http_status": 401}

    log_context: str
    if workspace_id:
        url = f"{PBI_API_BASE_URL_MYORG}/groups/{workspace_id}/reports/{report_id}/ExportToFile"
        log_context = f"reporte '{report_id}' en workspace '{workspace_id}'"
    else:
        url = f"{PBI_API_BASE_URL_MYORG}/reports/{report_id}/ExportToFile"
        log_context = f"reporte '{report_id}' (My Workspace/Org)"
        logger.warning(f"Exportando reporte '{report_id}' sin workspace_id. Contexto es My Workspace u organización.")

    payload: Dict[str, Any] = {"format": export_format}
    powerBIReportConfiguration: Dict[str, Any] = {}
    if report_level_filters:
        # La estructura del filtro es más compleja, ej: {"reportLevelFilters": [{"filter": "Store/Territory eq 'NC'"}]}
        # Por simplicidad, asumimos que el usuario pasa el objeto correcto si lo necesita.
        # Esto es un ejemplo básico.
        # powerBIReportConfiguration["reportLevelFilters"] = report_level_filters # Consultar doc para formato exacto
        logger.warning("El filtrado a nivel de reporte para exportación no está completamente implementado en 'report_level_filters', requiere formato específico.")

    if page_name:
        # Para exportar una página específica, se debe configurar `reportPages`
        # dentro de `powerBIReportConfiguration`.
        # Ejemplo: "pages": [{"pageName": "ReportSection1"}]
        # powerBIReportConfiguration.setdefault("pages", []).append({"pageName": page_name})
        logger.warning("La exportación de página específica ('page_name') no está completamente implementada, requiere formato de 'pages' en config.")


    # if powerBIReportConfiguration: # Si se ha configurado algo
    #     payload["powerBIReportConfiguration"] = powerBIReportConfiguration

    logger.info(f"Iniciando exportación de {log_context} a formato {export_format}")
    try:
        response = requests.post(url, headers=pbi_headers, json=payload, timeout=PBI_API_CALL_TIMEOUT)
        # La API devuelve 202 Accepted si la solicitud de exportación fue exitosa.
        # El cuerpo de la respuesta contiene un objeto Export con un 'id' que se usa para verificar el estado.
        if response.status_code == 202:
            export_job_details = response.json()
            export_id = export_job_details.get("id")
            logger.info(f"Exportación iniciada para {log_context}. Export ID: {export_id}. Estado: {export_job_details.get('status')}")
            return {
                "status": "success", 
                "message": "Exportación de reporte iniciada.",
                "export_id": export_id,
                "report_id": report_id,
                "current_status": export_job_details.get('status'),
                "details": export_job_details,
                "http_status": 202
            }
        else:
            response.raise_for_status() # Lanza error para otros códigos
            return {"status": "warning", "message": f"Respuesta inesperada {response.status_code} al iniciar exportación.", "details": response.text, "http_status": response.status_code}

    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code
        logger.error(f"Error HTTP iniciando exportación para {log_context}: {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP al iniciar exportación: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error iniciando exportación para {log_context}: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al iniciar exportación: {type(e).__name__}", "details": str(e), "http_status": 500}

# --- FIN DEL MÓDULO actions/power_bi_actions.py ---