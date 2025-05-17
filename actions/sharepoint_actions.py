# MyHttpTrigger/actions/sharepoint_actions.py
import logging
import requests # Necesario para tipos de excepción y para PUT a uploadUrl de sesión
import os
import json
import csv
from io import StringIO
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone as dt_timezone

# Importar el cliente autenticado y las constantes
from shared.helpers.http_client import AuthenticatedHttpClient
from shared import constants

logger = logging.getLogger(__name__)

# --- Configuración Leída de Variables de Entorno o constants.py ---
SHAREPOINT_DEFAULT_SITE_ID = os.environ.get('SHAREPOINT_DEFAULT_SITE_ID', 
                                            getattr(constants, 'SHAREPOINT_DEFAULT_SITE_ID', None))
SHAREPOINT_DEFAULT_DRIVE_ID_OR_NAME = os.environ.get('SHAREPOINT_DEFAULT_DRIVE_ID_OR_NAME', 
                                                     getattr(constants, 'SHAREPOINT_DEFAULT_DRIVE_ID_OR_NAME', 'Documents'))
MEMORIA_LIST_NAME = getattr(constants, 'MEMORIA_LIST_NAME', 'AsistenteMemoria')

# --- Constantes de Scopes (con fallback a constants.GRAPH_SCOPE) ---
GRAPH_SCOPE_SITES_READ_ALL = getattr(constants, 'GRAPH_SCOPE_SITES_READ_ALL', constants.GRAPH_SCOPE)
GRAPH_SCOPE_SITES_MANAGE_ALL = getattr(constants, 'GRAPH_SCOPE_SITES_MANAGE_ALL', constants.GRAPH_SCOPE)
GRAPH_SCOPE_SITES_FULLCONTROL_ALL = getattr(constants, 'GRAPH_SCOPE_SITES_FULLCONTROL_ALL', constants.GRAPH_SCOPE)
GRAPH_SCOPE_FILES_READ_ALL = getattr(constants, 'GRAPH_SCOPE_FILES_READ_ALL', constants.GRAPH_SCOPE)
GRAPH_SCOPE_FILES_READ_WRITE_ALL = getattr(constants, 'GRAPH_SCOPE_FILES_READ_WRITE_ALL', constants.GRAPH_SCOPE)

def _log_scope_fallback_warnings_sp(): # Renombrado para evitar colisión con otros módulos si se copiara
    scopes_to_check = {
        "GRAPH_SCOPE_SITES_READ_ALL": GRAPH_SCOPE_SITES_READ_ALL,
        "GRAPH_SCOPE_SITES_MANAGE_ALL": GRAPH_SCOPE_SITES_MANAGE_ALL,
        "GRAPH_SCOPE_SITES_FULLCONTROL_ALL": GRAPH_SCOPE_SITES_FULLCONTROL_ALL,
        "GRAPH_SCOPE_FILES_READ_ALL": GRAPH_SCOPE_FILES_READ_ALL,
        "GRAPH_SCOPE_FILES_READ_WRITE_ALL": GRAPH_SCOPE_FILES_READ_WRITE_ALL,
    }
    for name, actual_scope_val_list in scopes_to_check.items():
        if actual_scope_val_list and constants.GRAPH_SCOPE and \
           isinstance(actual_scope_val_list, list) and isinstance(constants.GRAPH_SCOPE, list) and \
           actual_scope_val_list[0] == constants.GRAPH_SCOPE[0] and name != "GRAPH_SCOPE": # Evitar warning para GRAPH_SCOPE mismo
            logger.warning(f"SharePoint: Usando GRAPH_SCOPE general para una operación que podría beneficiarse de '{name}'. Considere definir '{name}' en constants.py.")
_log_scope_fallback_warnings_sp()

# --- Helper para validar si un input parece un Graph Site ID ---
def _is_valid_graph_site_id_format(site_id_string: str) -> bool: # Sin cambios
    if not site_id_string:
        return False
    is_composite_id = ',' in site_id_string and site_id_string.count(',') >= 1
    is_server_relative_path = ':' in site_id_string and ('/sites/' in site_id_string or '/teams/' in site_id_string)
    is_graph_path_segment = site_id_string.startswith('sites/') and '{' in site_id_string and '}' in site_id_string
    is_root = site_id_string.lower() == "root"
    return is_composite_id or is_server_relative_path or is_graph_path_segment or is_root

# --- Helper Interno para Obtener Site ID (versión robusta) ---
def _obtener_site_id_sp(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> str: # Sin cambios en la lógica interna, solo el nombre
    site_input: Optional[str] = params.get("site_id") or params.get("site_identifier")

    if site_input:
        if _is_valid_graph_site_id_format(site_input):
            logger.debug(f"Se proporcionó un Site ID con formato Graph reconocido: '{site_input}'. Usándolo directamente.")
            return site_input
        
        lookup_path = site_input
        if not ':' in site_input and (site_input.startswith("/sites/") or site_input.startswith("/teams/")):
             try:
                 root_site_info_resp = client.get(f"{constants.GRAPH_API_BASE_URL}/sites/root?$select=siteCollection", scope=GRAPH_SCOPE_SITES_READ_ALL)
                 root_site_hostname = root_site_info_resp.json().get("siteCollection", {}).get("hostname")
                 if root_site_hostname:
                     lookup_path = f"{root_site_hostname}:{site_input}"
                     logger.info(f"Path relativo '{site_input}' convertido a path completo para búsqueda: '{lookup_path}'")
                 else:
                     logger.warning(f"No se pudo obtener hostname del sitio raíz para resolver path relativo '{site_input}'. Se intentará buscar tal cual.")
             except Exception as e_root_host:
                 logger.warning(f"Error obteniendo hostname del sitio raíz para path relativo '{site_input}': {e_root_host}. Se intentará buscar tal cual.")
        
        url_lookup = f"{constants.GRAPH_API_BASE_URL}/sites/{lookup_path}?$select=id,displayName,webUrl,siteCollection"
        logger.debug(f"Intentando obtener Site ID para '{lookup_path}' mediante: GET {url_lookup}")
        try:
            response = client.get(url_lookup, scope=GRAPH_SCOPE_SITES_READ_ALL)
            site_data = response.json()
            resolved_site_id = site_data.get("id") 
            if resolved_site_id:
                logger.info(f"Site ID resuelto para '{site_input}' (buscado como '{lookup_path}'): '{resolved_site_id}' (Nombre: {site_data.get('displayName')})")
                return resolved_site_id
            else:
                logger.warning(f"Respuesta de Graph API para '{lookup_path}' no contenía 'id'. Respuesta: {site_data}")
        except requests.exceptions.HTTPError as e:
            logger.warning(f"Error HTTP {e.response.status_code if e.response else 'N/A'} al buscar sitio por '{lookup_path}'. Error: {e.response.text if e.response else str(e)}. Se intentará fallback.")
        except Exception as e_other:
            logger.warning(f"Error inesperado buscando sitio por '{lookup_path}': {e_other}. Se intentará fallback.")

    if SHAREPOINT_DEFAULT_SITE_ID and _is_valid_graph_site_id_format(SHAREPOINT_DEFAULT_SITE_ID):
        logger.debug(f"Usando Site ID por defecto de la configuración: '{SHAREPOINT_DEFAULT_SITE_ID}'")
        return SHAREPOINT_DEFAULT_SITE_ID
    elif SHAREPOINT_DEFAULT_SITE_ID:
        logger.warning(f"SHAREPOINT_DEFAULT_SITE_ID ('{SHAREPOINT_DEFAULT_SITE_ID}') no tiene un formato de Graph ID válido. No se usará para resolución directa.")

    url_root_site = f"{constants.GRAPH_API_BASE_URL}/sites/root?$select=id,displayName"
    logger.debug(f"Intentando obtener el sitio raíz del tenant como último fallback: GET {url_root_site}")
    try:
        response_root = client.get(url_root_site, scope=GRAPH_SCOPE_SITES_READ_ALL)
        root_site_data = response_root.json()
        root_site_id = root_site_data.get("id")
        if root_site_id:
            logger.info(f"Usando Site ID raíz del tenant como fallback: '{root_site_id}' (Nombre: {root_site_data.get('displayName')})")
            return root_site_id
    except Exception as e_root:
        logger.critical(f"Fallo CRÍTICO al obtener Site ID (ni input, ni default de config, ni raíz del tenant funcionaron). Error: {e_root}", exc_info=True)
        raise ValueError(f"No se pudo determinar el Site ID de SharePoint. Verifique la configuración o el parámetro 'site_id'. Error: {e_root}")

    msg = "No se pudo determinar un Site ID válido de SharePoint a partir de la entrada, configuración por defecto o sitio raíz."
    logger.critical(msg)
    raise ValueError(msg)

# --- Helper Interno para Obtener Drive ID ---
def _get_drive_id(client: AuthenticatedHttpClient, site_id: str, drive_id_or_name_input: Optional[str] = None) -> str: # Sin cambios en la lógica interna, solo el nombre
    target_drive_identifier = drive_id_or_name_input or SHAREPOINT_DEFAULT_DRIVE_ID_OR_NAME
    if not target_drive_identifier:
        raise ValueError("Se requiere un nombre o ID de Drive (biblioteca).")

    is_likely_id = '!' in target_drive_identifier or (len(target_drive_identifier) > 30 and not any(c in target_drive_identifier for c in [' ', '/']))
    
    if is_likely_id:
        url_drive_by_id = f"{constants.GRAPH_API_BASE_URL}/sites/{site_id}/drives/{target_drive_identifier}?$select=id,name"
        logger.debug(f"Intentando obtener Drive por ID: '{target_drive_identifier}' en sitio '{site_id}'. GET {url_drive_by_id}")
        try:
            response = client.get(url_drive_by_id, scope=GRAPH_SCOPE_FILES_READ_ALL)
            drive_data = response.json()
            drive_id = drive_data.get("id")
            if drive_id:
                logger.info(f"Drive ID '{drive_id}' (Nombre: {drive_data.get('name')}) confirmado para entrada '{target_drive_identifier}'.")
                return drive_id
        except requests.exceptions.HTTPError as e_http:
            if e_http.response and e_http.response.status_code == 404:
                logger.warning(f"Drive con ID '{target_drive_identifier}' no encontrado en sitio '{site_id}'. Se intentará buscar por nombre.")
            else:
                logger.warning(f"Error HTTP ({e_http.response.status_code if e_http.response else 'N/A'}) al obtener Drive por ID '{target_drive_identifier}'. Se intentará buscar por nombre. Error: {e_http}")
        except Exception as e_other:
            logger.warning(f"Error inesperado al obtener Drive por ID '{target_drive_identifier}': {e_other}. Se intentará buscar por nombre.")

    url_list_drives = f"{constants.GRAPH_API_BASE_URL}/sites/{site_id}/drives?$select=id,name,displayName,webUrl"
    logger.debug(f"Listando Drives en sitio '{site_id}' para encontrar por nombre: '{target_drive_identifier}'. GET {url_list_drives}")
    try:
        response_drives = client.get(url_list_drives, scope=GRAPH_SCOPE_FILES_READ_ALL)
        drives_list = response_drives.json().get("value", [])
        
        for drive_obj in drives_list:
            if drive_obj.get("name", "").lower() == target_drive_identifier.lower() or \
               drive_obj.get("displayName", "").lower() == target_drive_identifier.lower():
                drive_id = drive_obj.get("id")
                if drive_id:
                    logger.info(f"Drive ID '{drive_id}' encontrado por nombre/displayName '{target_drive_identifier}' (Nombre real: {drive_obj.get('name')}, DisplayName: {drive_obj.get('displayName')}).")
                    return drive_id
        
        available_drives = [(d.get("name"), d.get("displayName")) for d in drives_list]
        msg = f"No se encontró Drive con nombre o ID '{target_drive_identifier}' en el sitio '{site_id}'. Drives disponibles: {available_drives}"
        logger.error(msg)
        raise ValueError(msg)
        
    except Exception as e:
        logger.error(f"Error crítico obteniendo Drive ID para '{target_drive_identifier}' en sitio '{site_id}': {e}", exc_info=True)
        raise ConnectionError(f"No se pudo obtener el Drive ID para la biblioteca '{target_drive_identifier}': {e}") from e

# --- Helper para construir endpoint de item por Path ---
def _get_sp_item_endpoint_by_path(site_id: str, drive_id: str, item_path: str) -> str: # Sin cambios
    safe_path = item_path.strip()
    if not safe_path or safe_path == '/':
        return f"{constants.GRAPH_API_BASE_URL}/sites/{site_id}/drives/{drive_id}/root"
    if safe_path.startswith('/'):
        safe_path = safe_path[1:]
    return f"{constants.GRAPH_API_BASE_URL}/sites/{site_id}/drives/{drive_id}/root:/{safe_path}"

# --- Helper para construir endpoint de item por ID ---
def _get_sp_item_endpoint_by_id(site_id: str, drive_id: str, item_id: str) -> str: # Sin cambios
    return f"{constants.GRAPH_API_BASE_URL}/sites/{site_id}/drives/{drive_id}/items/{item_id}"

# --- Helper para manejar errores de Graph API de forma centralizada ---
def _handle_graph_api_error(e: Exception, action_name: str, params_for_log: Optional[Dict[str, Any]] = None) -> Dict[str, Any]: # Sin cambios
    log_message = f"Error en SharePoint action '{action_name}'"
    safe_params = {}
    if params_for_log:
        sensitive_keys = ['valor', 'content_bytes', 'nuevos_valores_campos', 'datos_campos', 
                          'metadata_updates', 'password', 'columnas', 'update_payload', 
                          'recipients_payload', 'body', 'payload']
        safe_params = {k: (v if k not in sensitive_keys else "[CONTENIDO OMITIDO]") for k, v in params_for_log.items()}
        log_message += f" con params: {safe_params}"
    
    logger.error(f"{log_message}: {type(e).__name__} - {str(e)}", exc_info=True)
    
    details = str(e)
    status_code = 500
    graph_error_code = None

    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
        status_code = e.response.status_code
        try:
            error_data = e.response.json()
            error_info = error_data.get("error", {})
            details = error_info.get("message", e.response.text)
            graph_error_code = error_info.get("code")
        except json.JSONDecodeError:
            details = e.response.text
            
    return {
        "status": "error",
        "action": action_name,
        "message": f"Error ejecutando {action_name}: {type(e).__name__}",
        "http_status": status_code,
        "details": details,
        "graph_error_code": graph_error_code
    }

# --- Helper para obtener timestamp actual sin microsegundos y en formato ISO UTC 'Z' ---
def _get_current_timestamp_iso_z() -> str: # Sin cambios
    return datetime.now(dt_timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

# --- Helper para paginación de resultados de SharePoint ---
def _sp_paged_request( # Sin cambios en la lógica interna, solo el nombre
    client: AuthenticatedHttpClient,
    url_base: str,
    scope: List[str], 
    params_input: Dict[str, Any], 
    query_api_params_initial: Dict[str, Any], 
    max_items_total: Optional[int],
    action_name_for_log: str
) -> Dict[str, Any]:
    all_items: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0
    max_pages_to_fetch = constants.MAX_PAGING_PAGES 

    top_value_initial = query_api_params_initial.get('$top', constants.DEFAULT_PAGING_SIZE)

    logger.info(f"Iniciando solicitud paginada para '{action_name_for_log}' desde '{url_base.split('?')[0]}...'. "
                f"Max total items: {max_items_total or 'todos'}, por página: {top_value_initial}, max_páginas: {max_pages_to_fetch}")
    try:
        while current_url and (max_items_total is None or len(all_items) < max_items_total) and page_count < max_pages_to_fetch:
            page_count += 1
            is_first_call = (page_count == 1)
            
            current_params_for_call = query_api_params_initial if is_first_call and current_url == url_base else None
            logger.debug(f"Página {page_count} para '{action_name_for_log}': GET {current_url.split('?')[0]} con params: {current_params_for_call}")
            
            response = client.get(url=current_url, scope=scope, params=current_params_for_call)
            response_data = response.json()
            
            page_items = response_data.get('value', [])
            if not isinstance(page_items, list):
                logger.warning(f"Respuesta inesperada en paginación para '{action_name_for_log}', 'value' no es una lista. Respuesta: {response_data}")
                break 
            
            for item in page_items:
                if max_items_total is None or len(all_items) < max_items_total:
                    all_items.append(item)
                else:
                    break 
            
            current_url = response_data.get('@odata.nextLink')
            if not current_url or (max_items_total is not None and len(all_items) >= max_items_total):
                logger.debug(f"'{action_name_for_log}': Fin de paginación. nextLink: {'Sí' if current_url else 'No'}, Items actuales: {len(all_items)}.")
                break
        
        if page_count >= max_pages_to_fetch and current_url:
            logger.warning(f"'{action_name_for_log}' alcanzó el límite de {max_pages_to_fetch} páginas procesadas. Pueden existir más resultados no recuperados.")

        logger.info(f"'{action_name_for_log}' recuperó {len(all_items)} items en {page_count} páginas.")
        return {
            "status": "success", 
            "data": {"value": all_items, "@odata.count": len(all_items)}, 
            "total_retrieved": len(all_items), 
            "pages_processed": page_count
        }
    except Exception as e:
        return _handle_graph_api_error(e, action_name_for_log, params_input)

# Helper interno para resolver item ID para SP si se da un path (revisado)
def _get_item_id_from_path_if_needed_sp( # Sin cambios, pero llamará a get_file_metadata (renombrado)
    client: AuthenticatedHttpClient, 
    item_path_or_id: str,
    site_id: str,
    drive_id: str,
) -> Union[str, Dict[str, Any]]:
    is_likely_id = not ('/' in item_path_or_id) and (len(item_path_or_id) > 40 or '!' in item_path_or_id)
    if is_likely_id:
        return item_path_or_id

    logger.debug(f"'{item_path_or_id}' parece un path en SP Drive. Intentando obtener su ID.")
    metadata_params = {
        "site_id": site_id, 
        "drive_id_or_name": drive_id,
        "item_id_or_path": item_path_or_id,
        "select": "id,name"
    }
    try:
        item_metadata_response = get_file_metadata(client, metadata_params) # LLAMADA A FUNCION RENOMBRADA
        
        if item_metadata_response.get("status") == "success":
            item_data = item_metadata_response.get("data", {})
            item_id = item_data.get("id")
            if item_id:
                logger.info(f"ID '{item_id}' (Nombre: {item_data.get('name')}) obtenido para path SP '{item_path_or_id}'.")
                return item_id
            else:
                error_msg = f"No se encontró 'id' en la respuesta de metadatos para el path SP '{item_path_or_id}'."
                logger.error(error_msg + f" Respuesta: {item_data}")
                return {"status": "error", "message": error_msg, "details": item_data}
        else: 
            error_msg = f"Fallo al obtener metadatos (y por tanto ID) para el path SP '{item_path_or_id}'."
            logger.error(error_msg + f" Detalles: {item_metadata_response}")
            return {"status": "error", "message": error_msg, "details": item_metadata_response}
    except Exception as e_meta:
        error_msg = f"Excepción al intentar obtener ID para path SP '{item_path_or_id}': {type(e_meta).__name__} - {e_meta}"
        logger.error(error_msg, exc_info=True)
        return {"status": "error", "message": error_msg, "details": str(e_meta)}

# --- Helper para asegurar que la lista de memoria exista (nombre interno) ---
def _ensure_memory_list_exists_internal(client: AuthenticatedHttpClient, site_id: str) -> bool:
    """Función interna para asegurar la lista. La pública será memory_ensure_list."""
    try:
        url_get_list = f"{constants.GRAPH_API_BASE_URL}/sites/{site_id}/lists/{MEMORIA_LIST_NAME}?$select=id"
        try:
            client.get(url_get_list, scope=GRAPH_SCOPE_SITES_READ_ALL)
            logger.info(f"Lista de memoria '{MEMORIA_LIST_NAME}' ya existe en sitio '{site_id}'.")
            return True
        except requests.exceptions.HTTPError as http_err:
            if http_err.response is not None and http_err.response.status_code == 404:
                logger.info(f"Lista de memoria '{MEMORIA_LIST_NAME}' no encontrada en sitio '{site_id}'. Intentando crearla...")
                columnas_default = [
                    {"name": "SessionID", "text": {}},
                    {"name": "Clave", "text": {}},
                    {"name": "Valor", "text": {"allowMultipleLines": True, "textType": "plain"}}, # Era multilineText, Graph API usa text con allowMultipleLines
                    {"name": "Timestamp", "dateTime": {"displayAs": "default", "format": "dateTime"}}
                ]
                create_params = {
                    "site_id": site_id, 
                    "nombre_lista": MEMORIA_LIST_NAME, # create_list espera "nombre_lista"
                    "columnas": columnas_default,
                    "template": "genericList"
                }
                # Llamada a la función pública renombrada create_list
                creation_response = create_list(client, create_params) 
                if creation_response.get("status") == "success":
                    logger.info(f"Lista de memoria '{MEMORIA_LIST_NAME}' creada exitosamente en sitio '{site_id}'.")
                    return True
                else:
                    logger.error(f"Fallo al crear lista de memoria '{MEMORIA_LIST_NAME}': {creation_response}")
                    return False
            else: # Otro error HTTP
                raise 
    except Exception as e:
        logger.error(f"Error crítico asegurando la existencia de la lista de memoria '{MEMORIA_LIST_NAME}' en sitio '{site_id}': {e}", exc_info=True)
        return False

# ============================================
# ==== ACCIONES PÚBLICAS (Nombres cortos según ACTION_MAP) ====
# ============================================

# ---- SITIOS ----
def get_site_info(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_get_site_info
    # La lógica es la misma que tenías en sp_get_site_info, solo se renombra.
    select_fields: Optional[str] = params.get("select")
    try:
        target_site_identifier = _obtener_site_id_sp(client, params)
        url = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_identifier}"
        query_api_params: Dict[str, str] = {}
        if select_fields: 
            query_api_params['$select'] = select_fields
        else: 
            query_api_params['$select'] = "id,displayName,name,webUrl,createdDateTime,lastModifiedDateTime,description,siteCollection"
            
        logger.info(f"Obteniendo información del sitio SP identificado como '{target_site_identifier}' (Select: {select_fields or 'default'})")
        response = client.get(url, scope=GRAPH_SCOPE_SITES_READ_ALL, params=query_api_params if query_api_params else None)
        return {"status": "success", "data": response.json()}
    except Exception as e:
        return _handle_graph_api_error(e, "get_site_info", params)

def search_sites(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_search_sites
    # Lógica igual a sp_search_sites
    query_text: Optional[str] = params.get("query_text")
    if not query_text:
        return _handle_graph_api_error(ValueError("'query_text' es un parámetro requerido para buscar sitios."), "search_sites", params)
    url = f"{constants.GRAPH_API_BASE_URL}/sites" # Endpoint es /sites, el param 'search' hace la búsqueda
    api_query_params: Dict[str, Any] = {'search': query_text}
    if params.get("select"): api_query_params["$select"] = params["select"]
    if params.get("top"): api_query_params["$top"] = params["top"] # Graph soporta $top aquí
    logger.info(f"Buscando sitios SP con query: '{query_text}' y params OData: { {k:v for k,v in api_query_params.items() if k != 'search'} }")
    try:
        response = client.get(url, scope=GRAPH_SCOPE_SITES_READ_ALL, params=api_query_params)
        return {"status": "success", "data": response.json()} 
    except Exception as e:
        return _handle_graph_api_error(e, "search_sites", params)

# ---- LISTAS ----
def create_list(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_create_list
    # Lógica igual a sp_create_list
    list_name: Optional[str] = params.get("nombre_lista") 
    columns_definition: Optional[List[Dict[str, Any]]] = params.get("columnas") 
    list_template: str = params.get("template", "genericList")
    if not list_name:
        return _handle_graph_api_error(ValueError("'nombre_lista' es un parámetro requerido."), "create_list", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        url = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_id}/lists"
        body_payload: Dict[str, Any] = {"displayName": list_name, "list": {"template": list_template}}
        if columns_definition and isinstance(columns_definition, list):
            body_payload["columns"] = columns_definition
        logger.info(f"Creando lista SP '{list_name}' (template: '{list_template}') en sitio '{target_site_id}'")
        response = client.post(url, scope=GRAPH_SCOPE_SITES_MANAGE_ALL, json_data=body_payload)
        return {"status": "success", "data": response.json()}
    except Exception as e:
        return _handle_graph_api_error(e, "create_list", params)

def list_lists(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_list_lists
    # Lógica igual a sp_list_lists
    select_fields: str = params.get("select", "id,name,displayName,webUrl,list")
    top_per_page: int = min(int(params.get('top_per_page', 50)), constants.DEFAULT_PAGING_SIZE)
    max_items_total: Optional[int] = params.get('max_items_total')
    filter_query: Optional[str] = params.get("filter_query")
    order_by: Optional[str] = params.get("order_by")
    expand_fields: Optional[str] = params.get("expand")
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        url_base = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_id}/lists"
        query_api_params_init: Dict[str, Any] = {'$top': top_per_page, '$select': select_fields}
        if filter_query: query_api_params_init['$filter'] = filter_query
        if order_by: query_api_params_init['$orderby'] = order_by
        if expand_fields: query_api_params_init['$expand'] = expand_fields
        return _sp_paged_request(client, url_base, GRAPH_SCOPE_SITES_READ_ALL, params, query_api_params_init, max_items_total, "list_lists")
    except Exception as e:
        return _handle_graph_api_error(e, "list_lists", params)

def get_list(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_get_list
    # Lógica igual a sp_get_list
    list_id_or_name: Optional[str] = params.get("lista_id_o_nombre")
    select_fields: Optional[str] = params.get("select")
    expand_fields: Optional[str] = params.get("expand") # Ej: "columns,fields"
    if not list_id_or_name:
        return _handle_graph_api_error(ValueError("'lista_id_o_nombre' es requerido."), "get_list", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        url = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_id}/lists/{list_id_or_name}"
        query_api_params: Dict[str, str] = {}
        if select_fields: query_api_params['$select'] = select_fields
        if expand_fields: query_api_params['$expand'] = expand_fields
        logger.info(f"Obteniendo lista SP '{list_id_or_name}' del sitio '{target_site_id}'")
        response = client.get(url, scope=GRAPH_SCOPE_SITES_READ_ALL, params=query_api_params if query_api_params else None)
        return {"status": "success", "data": response.json()}
    except Exception as e:
        return _handle_graph_api_error(e, "get_list", params)

def update_list(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_update_list
    # Lógica igual a sp_update_list
    list_id_or_name: Optional[str] = params.get("lista_id_o_nombre")
    update_payload: Optional[Dict[str, Any]] = params.get("update_payload")
    if not list_id_or_name or not update_payload or not isinstance(update_payload, dict):
        return _handle_graph_api_error(ValueError("'lista_id_o_nombre' y 'update_payload' (dict) son requeridos."), "update_list", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        url = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_id}/lists/{list_id_or_name}"
        logger.info(f"Actualizando lista SP '{list_id_or_name}' en sitio '{target_site_id}' con payload: {update_payload}")
        response = client.patch(url, scope=GRAPH_SCOPE_SITES_MANAGE_ALL, json_data=update_payload)
        return {"status": "success", "data": response.json()} # PATCH en lista devuelve el objeto actualizado
    except Exception as e:
        return _handle_graph_api_error(e, "update_list", params)

def delete_list(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_delete_list
    # Lógica igual a sp_delete_list
    list_id_or_name: Optional[str] = params.get("lista_id_o_nombre")
    if not list_id_or_name:
        return _handle_graph_api_error(ValueError("'lista_id_o_nombre' es requerido."), "delete_list", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        url = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_id}/lists/{list_id_or_name}"
        logger.info(f"Eliminando lista SP '{list_id_or_name}' del sitio '{target_site_id}'")
        response = client.delete(url, scope=GRAPH_SCOPE_SITES_MANAGE_ALL) # Devuelve 204 No Content
        return {"status": "success", "message": f"Lista '{list_id_o_name}' eliminada exitosamente.", "http_status": response.status_code}
    except Exception as e:
        return _handle_graph_api_error(e, "delete_list", params)

# ---- ITEMS DE LISTA ----
def add_list_item(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_add_list_item
    # Lógica igual a sp_add_list_item
    list_id_or_name: Optional[str] = params.get("lista_id_o_nombre")
    fields_data: Optional[Dict[str, Any]] = params.get("datos_campos") # Renombrado en el original, aquí usamos "fields_data" consistentemente
    if not list_id_or_name:
        return _handle_graph_api_error(ValueError("'lista_id_o_nombre' es requerido."), "add_list_item", params)
    if not fields_data or not isinstance(fields_data, dict):
        return _handle_graph_api_error(ValueError("'fields_data' (diccionario con los campos del item) es requerido."), "add_list_item", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        # El payload para crear un item es {"fields": {...campos...}}
        body_payload = {"fields": fields_data}
        url = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_id}/lists/{list_id_or_name}/items"
        logger.info(f"Agregando elemento a lista SP '{list_id_or_name}' en sitio '{target_site_id}' con campos: {list(fields_data.keys())}")
        response = client.post(url, scope=GRAPH_SCOPE_SITES_MANAGE_ALL, json_data=body_payload)
        return {"status": "success", "data": response.json()} # Devuelve el item creado
    except Exception as e:
        return _handle_graph_api_error(e, "add_list_item", params)

def list_list_items(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_list_list_items
    # Lógica igual a sp_list_list_items
    list_id_or_name: Optional[str] = params.get("lista_id_o_nombre")
    if not list_id_or_name:
        return _handle_graph_api_error(ValueError("'lista_id_o_nombre' es requerido."), "list_list_items", params)

    select_fields: Optional[str] = params.get("select")
    filter_query: Optional[str] = params.get("filter_query")
    # Por defecto, Graph expande 'fields'. Si se quiere ser explícito o añadir más:
    expand_fields: str = params.get("expand", "fields(select=*)") # Expandir todos los campos por defecto
    top_per_page: int = min(int(params.get('top_per_page', 50)), constants.DEFAULT_PAGING_SIZE)
    max_items_total: Optional[int] = params.get('max_items_total')
    order_by: Optional[str] = params.get("orderby")

    try:
        target_site_id = _obtener_site_id_sp(client, params)
        url_base = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_id}/lists/{list_id_or_name}/items"
        
        query_api_params_init: Dict[str, Any] = {'$top': top_per_page}
        if select_fields: query_api_params_init["$select"] = select_fields
        if filter_query: query_api_params_init["$filter"] = filter_query
        if expand_fields: query_api_params_init["$expand"] = expand_fields
        if order_by: query_api_params_init["$orderby"] = order_by
        
        return _sp_paged_request(client, url_base, GRAPH_SCOPE_SITES_READ_ALL, params, query_api_params_init, max_items_total, "list_list_items")
    except Exception as e:
        return _handle_graph_api_error(e, "list_list_items", params)

def get_list_item(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_get_list_item
    # Lógica igual a sp_get_list_item
    list_id_or_name: Optional[str] = params.get("lista_id_o_nombre")
    item_id: Optional[str] = params.get("item_id") # ID del ListItem
    select_fields: Optional[str] = params.get("select")
    expand_fields: Optional[str] = params.get("expand", "fields(select=*)") # Expandir todos los campos por defecto
    if not list_id_or_name or not item_id:
        return _handle_graph_api_error(ValueError("'lista_id_o_nombre' e 'item_id' son requeridos."), "get_list_item", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        url = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_id}/lists/{list_id_or_name}/items/{item_id}"
        query_api_params: Dict[str, str] = {}
        if select_fields: query_api_params["$select"] = select_fields
        if expand_fields: query_api_params["$expand"] = expand_fields
        
        logger.info(f"Obteniendo item '{item_id}' de lista SP '{list_id_or_name}', sitio '{target_site_id}'")
        response = client.get(url, scope=GRAPH_SCOPE_SITES_READ_ALL, params=query_api_params if query_api_params else None)
        return {"status": "success", "data": response.json()}
    except Exception as e:
        return _handle_graph_api_error(e, "get_list_item", params)

def update_list_item(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_update_list_item
    # Lógica igual a sp_update_list_item
    list_id_or_name: Optional[str] = params.get("lista_id_o_nombre")
    item_id: Optional[str] = params.get("item_id")
    fields_to_update: Optional[Dict[str, Any]] = params.get("nuevos_valores_campos") # En el original era "nuevos_valores_campos"
    etag: Optional[str] = params.get("etag") # ETag del ListItem para concurrencia

    if not list_id_or_name or not item_id:
        return _handle_graph_api_error(ValueError("'lista_id_o_nombre' e 'item_id' son requeridos."), "update_list_item", params)
    if not fields_to_update or not isinstance(fields_to_update, dict):
        return _handle_graph_api_error(ValueError("'fields_to_update' (diccionario con los campos a actualizar) es requerido."), "update_list_item", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        # Para actualizar campos de un ListItem, se hace PATCH a .../items/{item-id}/fields
        url = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_id}/lists/{list_id_o_nombre}/items/{item_id}/fields"
        request_headers = {'If-Match': etag} if etag else {}
        logger.info(f"Actualizando campos del item '{item_id}' en lista SP '{list_id_o_nombre}', sitio '{target_site_id}'")
        response = client.patch(url, scope=GRAPH_SCOPE_SITES_MANAGE_ALL, json_data=fields_to_update, headers=request_headers)
        return {"status": "success", "data": response.json()} # Devuelve el FieldValueSet actualizado
    except Exception as e:
        return _handle_graph_api_error(e, "update_list_item", params)

def delete_list_item(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_delete_list_item
    # Lógica igual a sp_delete_list_item
    list_id_or_name: Optional[str] = params.get("lista_id_o_nombre")
    item_id: Optional[str] = params.get("item_id")
    etag: Optional[str] = params.get("etag") # Opcional, para borrado condicional
    if not list_id_or_name or not item_id:
        return _handle_graph_api_error(ValueError("'lista_id_o_nombre' e 'item_id' son requeridos."), "delete_list_item", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        url = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_id}/lists/{list_id_o_nombre}/items/{item_id}"
        request_headers = {'If-Match': etag} if etag else {}
        logger.info(f"Eliminando item '{item_id}' de lista SP '{list_id_o_nombre}', sitio '{target_site_id}'")
        response = client.delete(url, scope=GRAPH_SCOPE_SITES_MANAGE_ALL, headers=request_headers) # Devuelve 204 No Content
        return {"status": "success", "message": f"Item '{item_id}' eliminado exitosamente de la lista.", "http_status": response.status_code}
    except Exception as e:
        return _handle_graph_api_error(e, "delete_list_item", params)

def search_list_items(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_search_list_items
    # Lógica igual a sp_search_list_items, que reutiliza list_list_items con un $filter.
    list_id_or_name: Optional[str] = params.get("lista_id_o_nombre")
    query_text_as_filter: Optional[str] = params.get("query_text") # Se asume que esto es un $filter válido
    select_fields: Optional[str] = params.get("select")
    max_results: Optional[int] = params.get("top") # Para limitar, pasado a max_items_total

    if not list_id_or_name or not query_text_as_filter:
        return _handle_graph_api_error(ValueError("'lista_id_o_nombre' y 'query_text' (usado como $filter) son requeridos."), "search_list_items", params)
    
    logger.warning("La función 'search_list_items' actualmente interpreta 'query_text' como un parámetro '$filter' de OData. Para búsquedas de texto completo en SharePoint, considere usar la API de Búsqueda de Microsoft Graph (/search/query).")
    try:
        target_site_id = _obtener_site_id_sp(client, params) # Para pasar a list_list_items
        list_items_params = {
            "site_id": target_site_id, # Necesario para _obtener_site_id_sp dentro de list_list_items si no se pasa explícitamente
            "lista_id_o_nombre": list_id_or_name,
            "filter_query": query_text_as_filter,
            "select": select_fields,
            "max_items_total": max_results, # list_list_items lo usa
            "expand": params.get("expand", "fields(select=*)") # Mantener expansión de campos
        }
        # Llamar a la función renombrada list_list_items
        return list_list_items(client, list_items_params)
    except Exception as e:
        return _handle_graph_api_error(e, "search_list_items", params)

# ---- DOCUMENTOS Y BIBLIOTECAS (DRIVES) ----
def list_document_libraries(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_list_document_libraries
    # Lógica igual a sp_list_document_libraries
    select_fields: str = params.get("select", "id,name,displayName,webUrl,driveType,quota,owner")
    top_per_page: int = min(int(params.get('top_per_page', 50)), constants.DEFAULT_PAGING_SIZE)
    max_items_total: Optional[int] = params.get('max_items_total')
    filter_query: Optional[str] = params.get("filter_query") # Ej: "driveType eq 'documentLibrary'"
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        url_base = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_id}/drives"
        query_api_params_init: Dict[str, Any] = {'$top': top_per_page, '$select': select_fields}
        if filter_query: query_api_params_init['$filter'] = filter_query
        else: query_api_params_init['$filter'] = "driveType eq 'documentLibrary'" # Por defecto, solo bibliotecas
        return _sp_paged_request(client, url_base, GRAPH_SCOPE_FILES_READ_ALL, params, query_api_params_init, max_items_total, "list_document_libraries")
    except Exception as e:
        return _handle_graph_api_error(e, "list_document_libraries", params)

def list_folder_contents(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_list_folder_contents
    # Lógica igual a sp_list_folder_contents
    folder_path_or_id: str = params.get("folder_path_or_id", "") # Path relativo a la raíz del drive, o ID del folder
    drive_id_or_name_input: Optional[str] = params.get("drive_id_or_name") 
    select_fields: Optional[str] = params.get("select")
    expand_fields: Optional[str] = params.get("expand")
    top_per_page: int = min(int(params.get('top_per_page', 50)), 200) # Max para /children es 200
    max_items_total: Optional[int] = params.get('max_items_total')
    order_by: Optional[str] = params.get("orderby")
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        target_drive_id = _get_drive_id(client, target_site_id, drive_id_or_name_input)
        
        # Determinar si folder_path_or_id es un ID o un path
        is_folder_id = not ('/' in folder_path_or_id) and (len(folder_path_or_id) > 40 or '!' in folder_path_or_id)
        
        item_segment: str
        if is_folder_id:
            item_segment = f"items/{folder_path_or_id}"
            logger.info(f"Listando contenido de carpeta por ID '{folder_path_or_id}' en Drive '{target_drive_id}'")
        elif not folder_path_or_id or folder_path_or_id == "/": # Raíz del drive
            item_segment = "root"
            logger.info(f"Listando contenido de la raíz del Drive '{target_drive_id}'")
        else: # Es un path
            clean_path = folder_path_or_id.strip("/")
            item_segment = f"root:/{clean_path}"
            logger.info(f"Listando contenido de carpeta por path '{clean_path}' en Drive '{target_drive_id}'")
            
        url_base = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_id}/drives/{target_drive_id}/{item_segment}/children"

        query_api_params_init: Dict[str, Any] = {'$top': top_per_page}
        if select_fields: 
            query_api_params_init["$select"] = select_fields
        else: # Select por defecto para items
            query_api_params_init["$select"] = "id,name,webUrl,size,createdDateTime,lastModifiedDateTime,file,folder,package,parentReference"
        if expand_fields: query_api_params_init["$expand"] = expand_fields
        if order_by: query_api_params_init["$orderby"] = order_by
        
        return _sp_paged_request(client, url_base, GRAPH_SCOPE_FILES_READ_ALL, params, query_api_params_init, max_items_total, "list_folder_contents")
    except Exception as e:
        return _handle_graph_api_error(e, "list_folder_contents", params)

def get_file_metadata(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_get_file_metadata
    # Lógica igual a sp_get_file_metadata
    item_id_or_path: Optional[str] = params.get("item_id_or_path")
    drive_id_or_name_input: Optional[str] = params.get("drive_id_or_name")
    select_fields: Optional[str] = params.get("select")
    expand_fields: Optional[str] = params.get("expand")
    if not item_id_or_path:
        return _handle_graph_api_error(ValueError("'item_id_or_path' es requerido."),"get_file_metadata", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        target_drive_id = _get_drive_id(client, target_site_id, drive_id_or_name_input)

        is_item_id = not ('/' in item_id_or_path) and (len(item_id_or_path) > 40 or '!' in item_id_or_path)
        
        base_url_item: str
        if is_item_id:
            base_url_item = _get_sp_item_endpoint_by_id(target_site_id, target_drive_id, item_id_or_path)
        else:
            base_url_item = _get_sp_item_endpoint_by_path(target_site_id, target_drive_id, item_id_or_path)
        
        query_api_params: Dict[str, str] = {}
        if select_fields: 
            query_api_params["$select"] = select_fields
        else: # Select por defecto
            query_api_params["$select"] = "id,name,webUrl,size,createdDateTime,lastModifiedDateTime,file,folder,package,parentReference,listItem"
        if expand_fields: query_api_params["$expand"] = expand_fields # ej: "listItem(select=id,fields)"
        
        logger.info(f"Obteniendo metadatos para item '{item_id_or_path}' en drive '{target_drive_id}', sitio '{target_site_id}'")
        response = client.get(base_url_item, scope=GRAPH_SCOPE_FILES_READ_ALL, params=query_api_params if query_api_params else None)
        return {"status": "success", "data": response.json()}
    except Exception as e:
        return _handle_graph_api_error(e, "get_file_metadata", params)

def upload_document(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_upload_document
    # Lógica igual a sp_upload_document
    filename: Optional[str] = params.get("filename")
    content_bytes: Optional[bytes] = params.get("content_bytes")
    folder_path: str = params.get("folder_path", "") # Path relativo a la raíz del drive
    drive_id_or_name_input: Optional[str] = params.get("drive_id_or_name")
    conflict_behavior: str = params.get("conflict_behavior", "rename") # "fail", "replace", o "rename"

    if not filename or content_bytes is None: # content_bytes puede ser b"" para archivo vacío
        return _handle_graph_api_error(ValueError("'filename' y 'content_bytes' son requeridos."), "upload_document", params)
    if not isinstance(content_bytes, bytes):
        return _handle_graph_api_error(TypeError("'content_bytes' debe ser de tipo bytes."), "upload_document", params)

    try:
        target_site_id = _obtener_site_id_sp(client, params)
        target_drive_id = _get_drive_id(client, target_site_id, drive_id_or_name_input)

        path_segment = folder_path.strip("/")
        # El path para upload es relativo al root del drive y DEBE incluir el nombre del archivo.
        target_item_path_for_upload = f"{path_segment}/{filename}" if path_segment else filename
        
        # Construir la URL base para el item (con el nombre de archivo)
        item_upload_base_url = _get_sp_item_endpoint_by_path(target_site_id, target_drive_id, target_item_path_for_upload)
        
        file_size_bytes = len(content_bytes)
        logger.info(f"Iniciando subida de '{filename}' ({file_size_bytes} bytes) a Drive '{target_drive_id}', Path en Drive: '{target_item_path_for_upload}', Sitio: '{target_site_id}'. Comportamiento en conflicto: '{conflict_behavior}'.")

        if file_size_bytes <= 4 * 1024 * 1024: # Límite para subida simple es 4MB
            upload_url = f"{item_upload_base_url}/content" # PUT a .../nombrearchivo.ext:/content
            # El parámetro de conflicto se pasa en la URL para subidas simples
            put_query_params = {"@microsoft.graph.conflictBehavior": conflict_behavior}
            
            logger.debug(f"Usando subida simple: PUT {upload_url} con params {put_query_params}")
            response = client.put(
                upload_url, 
                scope=GRAPH_SCOPE_FILES_READ_WRITE_ALL, 
                data=content_bytes, 
                headers={"Content-Type": "application/octet-stream"}, # O el MIME type específico si se conoce
                params=put_query_params
            )
            return {"status": "success", "data": response.json()} # Devuelve el DriveItem
        else: # Sesión de carga para archivos grandes
            session_url = f"{item_upload_base_url}/createUploadSession"
            # El payload para createUploadSession incluye el item con el comportamiento de conflicto.
            session_body_payload = {"item": {"@microsoft.graph.conflictBehavior": conflict_behavior, "name": filename}}
            # Opcionalmente, se puede incluir "deferCommit": true si se quieren añadir más datos o metadatos antes del commit final.
            
            logger.debug(f"Archivo grande ({file_size_bytes} bytes). Creando sesión de carga: POST {session_url} con body: {session_body_payload}")
            session_response = client.post(session_url, scope=GRAPH_SCOPE_FILES_READ_WRITE_ALL, json_data=session_body_payload)
            upload_session_data = session_response.json()
            upload_url_from_session = upload_session_data.get("uploadUrl")
            
            if not upload_url_from_session:
                raise ValueError("No se pudo obtener 'uploadUrl' de la respuesta de la sesión de carga.")

            logger.info(f"Sesión de carga creada. Subiendo en chunks a: {upload_url_from_session.split('?')[0]}...")
            # La subida de chunks se hace con PUTs directos a la uploadUrl, no con AuthenticatedHttpClient
            # ya que esta URL ya está pre-autenticada y es externa a Graph API base.
            # Sin embargo, para mantener la consistencia y timeouts, podríamos encapsularlo.
            # Por ahora, usamos requests.put como en el código original.
            
            chunk_size = 5 * 1024 * 1024 # Tamaño de chunk recomendado (entre 5-10MB, debe ser múltiplo de 320KB)
            # Ajustar chunk_size a múltiplo de 320 KiB (320 * 1024 bytes) si la API lo requiere estrictamente.
            # Aquí usamos 5MB para simplificar.
            start_byte = 0
            final_response_json = None
            
            while start_byte < file_size_bytes:
                end_byte = min(start_byte + chunk_size - 1, file_size_bytes - 1)
                current_chunk_data = content_bytes[start_byte : end_byte + 1]
                chunk_len = len(current_chunk_data)
                
                headers_chunk_upload = {
                    "Content-Length": str(chunk_len), 
                    "Content-Range": f"bytes {start_byte}-{end_byte}/{file_size_bytes}"
                }
                logger.debug(f"Subiendo chunk: Rango {headers_chunk_upload['Content-Range']} ({chunk_len} bytes)")
                
                # Usar requests.put para la URL de sesión de carga
                chunk_upload_response = requests.put(
                    upload_url_from_session, 
                    data=current_chunk_data, 
                    headers=headers_chunk_upload,
                    timeout=constants.DEFAULT_API_TIMEOUT * 2 # Timeout más largo para subida de chunk
                )
                chunk_upload_response.raise_for_status() # Lanza error para 4xx/5xx
                
                response_status = chunk_upload_response.status_code
                if response_status in (200, 201): # Archivo completado (último chunk)
                    logger.info(f"Subida de chunk completada, archivo finalizado. Status: {response_status}")
                    final_response_json = chunk_upload_response.json() # DriveItem creado/actualizado
                    break 
                elif response_status == 202: # Chunk aceptado, esperando más
                    # La respuesta puede contener 'nextExpectedRanges'
                    next_ranges_info = chunk_upload_response.json().get('nextExpectedRanges', [f"{end_byte + 1}-"])
                    logger.debug(f"Chunk aceptado (202). Próximo byte esperado (rango): {next_ranges_info}")
                    # Actualizar start_byte basado en nextExpectedRanges si es necesario,
                    # o simplemente continuar con el siguiente chunk.
                    # Si nextExpectedRanges devuelve múltiples rangos, la lógica podría ser más compleja (para subidas interrumpidas).
                    # Para una subida secuencial simple:
                    start_byte = end_byte + 1 
                else: # Respuesta inesperada
                    msg_err_chunk = f"Respuesta inesperada {response_status} durante subida de chunk: {chunk_upload_response.text}"
                    logger.error(msg_err_chunk)
                    raise requests.exceptions.HTTPError(msg_err_chunk, response=chunk_upload_response)
            
            if final_response_json:
                return {"status": "success", "data": final_response_json, "message": "Archivo subido exitosamente mediante sesión de carga."}
            else: # Si el bucle termina sin una respuesta 200/201 final (ej. todos fueron 202)
                # Esto podría indicar que la sesión no se cerró correctamente o la API espera un commit final
                # si se usó deferCommit. Por ahora, asumimos que el último chunk 200/201 es el final.
                logger.warning("Subida de chunks completada, pero no se recibió una respuesta final 200/201 del servidor para el DriveItem.")
                return {"status": "warning", "message": "Subida de chunks completada, pero sin respuesta final del DriveItem. Verificar estado del archivo."}
                
    except Exception as e:
        return _handle_graph_api_error(e, "upload_document", params)

def download_document(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Union[bytes, Dict[str, Any]]: # Renombrado de sp_download_document
    # Lógica igual a sp_download_document
    item_id_or_path: Optional[str] = params.get("item_id_or_path")
    drive_id_or_name_input: Optional[str] = params.get("drive_id_or_name")
    if not item_id_or_path:
        return _handle_graph_api_error(ValueError("'item_id_or_path' es requerido."), "download_document", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        target_drive_id = _get_drive_id(client, target_site_id, drive_id_or_name_input)
        
        # Resolver a ID si es un path, ya que /content es más fiable con ID de item
        item_actual_id = _get_item_id_from_path_if_needed_sp(client, item_id_or_path, target_site_id, target_drive_id)
        if isinstance(item_actual_id, dict): # Error al resolver ID
            return item_actual_id

        # Endpoint para contenido de archivo: .../items/{item-id}/content
        url_content = f"{_get_sp_item_endpoint_by_id(target_site_id, target_drive_id, item_actual_id)}/content"
            
        logger.info(f"Descargando contenido de documento SP: ID '{item_actual_id}' (original: '{item_id_or_path}') desde drive '{target_drive_id}'")
        # client.get con stream=True y acceso a .content
        response = client.get(url_content, scope=GRAPH_SCOPE_FILES_READ_ALL, stream=True) # stream=True es importante para archivos
        file_bytes = response.content 
        logger.info(f"Documento SP '{item_actual_id}' descargado ({len(file_bytes)} bytes).")
        # Para devolver como archivo en Azure Functions, el trigger HTTP debe estar configurado
        # y se debe retornar un HttpResponse con el content_type y los bytes.
        # Aquí, devolvemos los bytes directamente, la capa superior decidirá cómo manejarlo.
        return file_bytes 
    except Exception as e:
        # Si se devuelve un error, debe ser un Dict, no bytes.
        return _handle_graph_api_error(e, "download_document", params)

# delete_item es la función base, delete_document la llamará.
def delete_item(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_delete_item
    # Lógica igual a sp_delete_item
    item_id_or_path: Optional[str] = params.get("item_id_or_path")
    drive_id_or_name_input: Optional[str] = params.get("drive_id_or_name")
    etag: Optional[str] = params.get("etag") # Para borrado condicional
    if not item_id_or_path:
        return _handle_graph_api_error(ValueError("'item_id_or_path' es requerido."),"delete_item", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        target_drive_id = _get_drive_id(client, target_site_id, drive_id_or_name_input)
        
        item_actual_id = _get_item_id_from_path_if_needed_sp(client, item_id_or_path, target_site_id, target_drive_id)
        if isinstance(item_actual_id, dict): return item_actual_id

        url_item = _get_sp_item_endpoint_by_id(target_site_id, target_drive_id, item_actual_id)
            
        request_headers = {'If-Match': etag} if etag else {}
        logger.info(f"Eliminando item '{item_id_or_path}' (ID: {item_actual_id}) de drive '{target_drive_id}', sitio '{target_site_id}'")
        response = client.delete(url_item, scope=GRAPH_SCOPE_FILES_READ_WRITE_ALL, headers=request_headers) # Devuelve 204 No Content
        return {"status": "success", "message": f"Item '{item_actual_id}' eliminado exitosamente.", "http_status": response.status_code}
    except Exception as e:
        return _handle_graph_api_error(e, "delete_item", params)

def delete_document(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Mapeada
    logger.debug("delete_document es un alias para delete_item.")
    return delete_item(client, params) # Llama a la función renombrada

def create_folder(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_create_folder (para DriveItem folder)
    # Lógica igual a sp_create_folder
    folder_name: Optional[str] = params.get("folder_name") # Nombre de la nueva carpeta
    # Path o ID de la carpeta padre donde se creará la nueva. Si es vacío/None, se crea en la raíz del drive.
    parent_folder_path_or_id: str = params.get("parent_folder_path_or_id", "") 
    drive_id_or_name_input: Optional[str] = params.get("drive_id_or_name")
    conflict_behavior: str = params.get("conflict_behavior", "fail") # "fail", "replace", o "rename"

    if not folder_name:
        return _handle_graph_api_error(ValueError("'folder_name' es un parámetro requerido."), "create_folder", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        target_drive_id = _get_drive_id(client, target_site_id, drive_id_or_name_input)
        
        # Obtener el endpoint de la carpeta padre
        parent_item_id_or_path_is_id = not ('/' in parent_folder_path_or_id) and (len(parent_folder_path_or_id) > 30 or '!' in parent_folder_path_or_id)

        parent_endpoint: str
        if parent_item_id_or_path_is_id:
            parent_endpoint = _get_sp_item_endpoint_by_id(target_site_id, target_drive_id, parent_folder_path_or_id)
        else: # Es path o raíz
            parent_endpoint = _get_sp_item_endpoint_by_path(target_site_id, target_drive_id, parent_folder_path_or_id)
            
        # El endpoint para crear una carpeta hija es .../{parent-item}/children
        url_create_folder = f"{parent_endpoint}/children"
        
        body_payload = {
            "name": folder_name, 
            "folder": {}, # Objeto vacío indica que es una carpeta
            "@microsoft.graph.conflictBehavior": conflict_behavior
        }
        logger.info(f"Creando carpeta '{folder_name}' en '{parent_folder_path_or_id if parent_folder_path_or_id else 'raíz'}' del drive '{target_drive_id}', sitio '{target_site_id}'")
        response = client.post(url_create_folder, scope=GRAPH_SCOPE_FILES_READ_WRITE_ALL, json_data=body_payload)
        return {"status": "success", "data": response.json()} # Devuelve el DriveItem de la carpeta creada
    except Exception as e:
        return _handle_graph_api_error(e, "create_folder", params)

def move_item(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_move_item
    # Lógica igual a sp_move_item
    item_id_or_path: Optional[str] = params.get("item_id_or_path")
    # ID (no path) de la carpeta de destino.
    target_parent_folder_id: Optional[str] = params.get("target_parent_folder_id") 
    new_name_after_move: Optional[str] = params.get("new_name") # Opcional, para renombrar al mover
    
    # Drive donde reside el item actualmente
    source_drive_id_or_name: Optional[str] = params.get("drive_id_or_name") or params.get("source_drive_id_or_name")
    # Drive de destino (si es diferente al de origen)
    target_drive_id_param: Optional[str] = params.get("target_drive_id")

    if not item_id_or_path or not target_parent_folder_id:
        return _handle_graph_api_error(ValueError("'item_id_or_path' y 'target_parent_folder_id' (ID de carpeta destino) son requeridos."), "move_item", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params) # Sitio donde está el item o donde se moverá (asumimos mismo sitio para simplificar si no se especifica target_site_id)
        source_drive_id_resolved = _get_drive_id(client, target_site_id, source_drive_id_or_name)
        
        # El item a mover DEBE ser referido por su ID para la operación PATCH
        item_actual_id = _get_item_id_from_path_if_needed_sp(client, item_id_or_path, target_site_id, source_drive_id_resolved)
        if isinstance(item_actual_id, dict): return item_actual_id # Error propagado
        
        # Endpoint para el PATCH es el item mismo
        url_patch_item = _get_sp_item_endpoint_by_id(target_site_id, source_drive_id_resolved, item_actual_id)
        
        payload_move: Dict[str, Any] = {"parentReference": {"id": target_parent_folder_id}}
        # Si el movimiento es a un Drive diferente (dentro del mismo sitio o a otro sitio)
        # se debe especificar driveId en parentReference.
        if target_drive_id_param:
            payload_move["parentReference"]["driveId"] = target_drive_id_param
            # Si el target_drive_id_param pertenece a un sitio diferente, se debe especificar siteId también.
            # Esta lógica puede volverse compleja si el movimiento es inter-sitio.
            # Por ahora, asumimos que si target_drive_id se da, es dentro del mismo sitio o el usuario maneja el contexto.
            if params.get("target_site_id"):
                 payload_move["parentReference"]["siteId"] = params.get("target_site_id")


        if new_name_after_move: 
            payload_move["name"] = new_name_after_move
        
        logger.info(f"Moviendo item '{item_id_or_path}' (ID: {item_actual_id}) a carpeta ID '{target_parent_folder_id}'" + (f" en drive ID '{target_drive_id_param}'" if target_drive_id_param else ""))
        response = client.patch(url_patch_item, scope=GRAPH_SCOPE_FILES_READ_WRITE_ALL, json_data=payload_move)
        return {"status": "success", "data": response.json()} # Devuelve el DriveItem actualizado
    except Exception as e:
        return _handle_graph_api_error(e, "move_item", params)

def copy_item(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_copy_item
    # Lógica igual a sp_copy_item
    item_id_or_path: Optional[str] = params.get("item_id_or_path") # Item a copiar
    # ID de la carpeta de destino donde se creará la copia.
    target_parent_folder_id: Optional[str] = params.get("target_parent_folder_id") 
    new_name_for_copy: Optional[str] = params.get("new_name") # Opcional, nombre para la copia
    
    source_site_id_param: Optional[str] = params.get("source_site_id") # Si el item fuente está en un sitio específico
    source_drive_id_or_name: Optional[str] = params.get("source_drive_id_or_name")
    
    target_site_id_param: Optional[str] = params.get("target_site_id") # Si el destino está en un sitio específico (puede ser el mismo o diferente)
    target_drive_id_param: Optional[str] = params.get("target_drive_id") # ID del drive destino

    if not item_id_or_path or not target_parent_folder_id:
        return _handle_graph_api_error(ValueError("'item_id_or_path' y 'target_parent_folder_id' son requeridos."), "copy_item", params)
    try:
        # Resolver sitio y drive de origen
        # Usar _obtener_site_id_sp con el source_site_id si se provee, o el 'site_id' general de params.
        source_site_id_resolved = _obtener_site_id_sp(client, {"site_id": source_site_id_param, **params} if source_site_id_param else params)
        source_drive_id_resolved = _get_drive_id(client, source_site_id_resolved, source_drive_id_or_name)
        
        item_actual_id = _get_item_id_from_path_if_needed_sp(client, item_id_or_path, source_site_id_resolved, source_drive_id_resolved)
        if isinstance(item_actual_id, dict): return item_actual_id

        # Endpoint para la acción de copia es sobre el item de origen
        url_copy_action = f"{_get_sp_item_endpoint_by_id(source_site_id_resolved, source_drive_id_resolved, item_actual_id)}/copy"
        
        # Construir la referencia al padre de destino
        parent_reference_payload: Dict[str, str] = {"id": target_parent_folder_id}
        if target_drive_id_param: # Si se especifica un drive de destino
            parent_reference_payload["driveId"] = target_drive_id_param
            # Si el drive de destino está en un sitio diferente al de origen (o se quiere ser explícito)
            if target_site_id_param:
                # _obtener_site_id_sp necesita los params originales para el fallback, o el ID directo.
                dest_site_id_resolved = _obtener_site_id_sp(client, {"site_id": target_site_id_param, **params})
                parent_reference_payload["siteId"] = dest_site_id_resolved 
            # Si no se da target_site_id_param, Graph asume que target_drive_id_param está en el mismo sitio que source_drive_id_resolved
            # o que es un ID de drive globalmente único (menos común para SharePoint).
            # Es más seguro si el usuario provee target_site_id si el drive está en otro sitio.

        body_payload: Dict[str, Any] = {"parentReference": parent_reference_payload}
        if new_name_for_copy: 
            body_payload["name"] = new_name_for_copy
        
        logger.info(f"Iniciando copia de item '{item_id_or_path}' (ID: {item_actual_id}) a carpeta ID '{target_parent_folder_id}'" + (f" en drive ID '{target_drive_id_param}'" if target_drive_id_param else ""))
        # La acción de copia es asíncrona, devuelve 202 Accepted y una URL para monitorear.
        response = client.post(url_copy_action, scope=GRAPH_SCOPE_FILES_READ_WRITE_ALL, json_data=body_payload)
        
        if response.status_code == 202: # Asíncrono
            monitor_url = response.headers.get("Location") # URL para monitorear el progreso
            # El cuerpo de la respuesta 202 podría estar vacío o contener info inicial.
            try: response_data = response.json() if response.content else {}
            except json.JSONDecodeError: response_data = {}
            logger.info(f"Solicitud de copia para item '{item_actual_id}' aceptada (202). URL de monitor: {monitor_url}. Data inicial: {response_data}")
            return {"status": "pending", "message": "Solicitud de copia de item aceptada y en progreso.", "monitor_url": monitor_url, "data": response_data, "http_status": 202}
        else: # Si fuera síncrono (raro para copia) o error
            logger.warning(f"Respuesta inesperada {response.status_code} al copiar item '{item_actual_id}'. Respuesta: {response.text[:300]}")
            return {"status": "success" if response.ok else "error", "data": response.json() if response.content else None, "http_status": response.status_code}
    except Exception as e:
        return _handle_graph_api_error(e, "copy_item", params)

def update_file_metadata(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_update_file_metadata
    # Lógica igual a sp_update_file_metadata
    item_id_or_path: Optional[str] = params.get("item_id_or_path")
    drive_id_or_name_input: Optional[str] = params.get("drive_id_or_name")
    # Payload con los campos del DriveItem a actualizar (ej. {"name": "nuevo_nombre.docx"})
    # O para campos de ListItem asociados: {"listItem": {"fields": {"MiColumna": "NuevoValor"}}}
    metadata_updates_payload: Optional[Dict[str, Any]] = params.get("metadata_updates") 
    etag: Optional[str] = params.get("etag") # ETag del DriveItem

    if not item_id_or_path or not metadata_updates_payload or not isinstance(metadata_updates_payload, dict):
        return _handle_graph_api_error(ValueError("'item_id_or_path' y 'metadata_updates' (dict) son requeridos."), "update_file_metadata", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        target_drive_id = _get_drive_id(client, target_site_id, drive_id_or_name_input)
        
        item_actual_id = _get_item_id_from_path_if_needed_sp(client, item_id_or_path, target_site_id, target_drive_id)
        if isinstance(item_actual_id, dict): return item_actual_id

        # Endpoint para actualizar metadatos de DriveItem
        url_update = _get_sp_item_endpoint_by_id(target_site_id, target_drive_id, item_actual_id)
        
        # Si se quieren actualizar campos de la lista asociada al documento (columnas personalizadas):
        # El payload sería, por ejemplo: {"listItem": {"fields": {"NombreColumna": "Valor"}}}
        # O se podría apuntar directamente a .../items/{item-id}/listItem/fields
        # Por ahora, esta función actualiza propiedades del DriveItem. Para ListItem fields, usar update_list_item.
        
        request_headers = {'If-Match': etag} if etag else {}
        logger.info(f"Actualizando metadatos para item '{item_id_or_path}' (ID: {item_actual_id}) con payload: {metadata_updates_payload}")
        response = client.patch(url_update, scope=GRAPH_SCOPE_FILES_READ_WRITE_ALL, json_data=metadata_updates_payload, headers=request_headers)
        return {"status": "success", "data": response.json()} # Devuelve el DriveItem actualizado
    except Exception as e:
        return _handle_graph_api_error(e, "update_file_metadata", params)

def create_sharing_link(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrada de sp_create_sharing_link
    # Lógica igual a la que tenías en sp_create_sharing_link
    item_id_or_path: Optional[str] = params.get("item_id_or_path")
    drive_id_or_name_input: Optional[str] = params.get("drive_id_or_name")
    link_type: str = params.get("link_type", "view") # "view", "edit", "embed"
    scope_param: str = params.get("scope", "organization") # "anonymous", "organization", "users" (users requiere specificPeople)
    password_link: Optional[str] = params.get("password") # Para links anónimos si la política lo permite
    expiration_datetime_str: Optional[str] = params.get("expiration_datetime") # ISO 8601 string
    # Para scope "users", se necesita 'recipients': [{"email": "user@example.com"}] o [{"objectId": "guid"}]
    recipients_payload: Optional[List[Dict[str,str]]] = params.get("recipients")

    if not item_id_or_path:
        return _handle_graph_api_error(ValueError("'item_id_or_path' es requerido."), "create_sharing_link", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        target_drive_id = _get_drive_id(client, target_site_id, drive_id_or_name_input)
        
        item_actual_id = _get_item_id_from_path_if_needed_sp(client, item_id_or_path, target_site_id, target_drive_id)
        if isinstance(item_actual_id, dict): return item_actual_id

        # Endpoint para la acción createLink
        url_action_createlink = f"{_get_sp_item_endpoint_by_id(target_site_id, target_drive_id, item_actual_id)}/createLink"
        
        body_payload_link: Dict[str, Any] = {"type": link_type, "scope": scope_param}
        if password_link: body_payload_link["password"] = password_link
        if expiration_datetime_str: body_payload_link["expirationDateTime"] = expiration_datetime_str # Debe ser ISO 8601
        if scope_param == "users" and recipients_payload:
            body_payload_link["recipients"] = recipients_payload
        elif scope_param == "users" and not recipients_payload:
             return _handle_graph_api_error(ValueError("Si scope es 'users', se requiere 'recipients'."), "create_sharing_link", params)

        logger.info(f"Creando enlace compartido para item '{item_id_or_path}' (ID: {item_actual_id}) tipo '{link_type}', scope '{scope_param}'")
        # Permisos: Files.ReadWrite, Files.ReadWrite.All, Sites.ReadWrite.All, Sites.FullControl.All
        # El permiso exacto puede depender del scope del enlace que se intenta crear.
        response = client.post(url_action_createlink, scope=GRAPH_SCOPE_FILES_READ_WRITE_ALL, json_data=body_payload_link)
        return {"status": "success", "data": response.json()} # Devuelve el objeto Permission con el enlace
    except Exception as e:
        return _handle_graph_api_error(e, "create_sharing_link", params)

def get_sharing_link(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Mapeada
    # Esta función es un alias de create_sharing_link si el objetivo es crear uno nuevo con ciertos parámetros.
    # Si el objetivo fuera listar enlaces existentes, la API es /permissions.
    # Dado el nombre, se asume que se quiere "obtener" un enlace (creándolo si es necesario).
    logger.debug("get_sharing_link es un alias para create_sharing_link con parámetros específicos.")
    return create_sharing_link(client, params)

# ---- PERMISOS DE ITEM ----
def list_item_permissions(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_list_item_permissions
    # Lógica igual a sp_list_item_permissions
    item_id_or_path: Optional[str] = params.get("item_id_or_path") # Para DriveItem
    drive_id_or_name_input: Optional[str] = params.get("drive_id_or_name") 
    list_id_or_name: Optional[str] = params.get("list_id_o_nombre") # Para ListItem
    list_item_id_param: Optional[str] = params.get("list_item_id") # ID del ListItem

    if not item_id_or_path and not (list_id_or_name and list_item_id_param):
        return _handle_graph_api_error(ValueError("Se requiere 'item_id_or_path' (para DriveItem) o ('list_id_o_nombre' y 'list_item_id') (para ListItem)."), "list_item_permissions", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        url_item_permissions: str
        log_item_description: str

        if item_id_or_path: # Es un DriveItem
            target_drive_id = _get_drive_id(client, target_site_id, drive_id_or_name_input)
            item_actual_id = _get_item_id_from_path_if_needed_sp(client, item_id_or_path, target_site_id, target_drive_id)
            if isinstance(item_actual_id, dict): return item_actual_id
            url_item_permissions = f"{_get_sp_item_endpoint_by_id(target_site_id, target_drive_id, item_actual_id)}/permissions"
            log_item_description = f"DriveItem ID '{item_actual_id}'"
        else: # Es un ListItem
            if not list_id_or_name or not list_item_id_param : # Doble check
                 return _handle_graph_api_error(ValueError("Para ListItem, 'list_id_o_nombre' y 'list_item_id' son requeridos."), "list_item_permissions", params)
            url_item_permissions = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_id}/lists/{list_id_or_name}/items/{list_item_id_param}/permissions"
            log_item_description = f"ListItem ID '{list_item_id_param}' en lista '{list_id_or_name}'"
        
        logger.info(f"Listando permisos para {log_item_description}")
        # Sites.FullControl.All es un scope amplio, pero leer permisos puede requerirlo o Files.ReadWrite.All si es DriveItem.
        response = client.get(url_item_permissions, scope=GRAPH_SCOPE_SITES_FULLCONTROL_ALL) 
        return {"status": "success", "data": response.json().get("value", [])} # Devuelve una colección de objetos Permission
    except Exception as e:
        return _handle_graph_api_error(e, "list_item_permissions", params)

def add_item_permissions(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de sp_add_item_permissions
    # Lógica igual a sp_add_item_permissions
    item_id_or_path: Optional[str] = params.get("item_id_or_path")
    drive_id_or_name_input: Optional[str] = params.get("drive_id_or_name")
    list_id_or_name: Optional[str] = params.get("list_id_o_nombre")
    list_item_id_param: Optional[str] = params.get("list_item_id")
    
    # Payload para la acción 'invite'
    recipients_payload: Optional[List[Dict[str,Any]]] = params.get("recipients") 
    roles_payload: Optional[List[str]] = params.get("roles") # ["read"], ["write"]
    require_signin: bool = params.get("requireSignIn", True) # Graph default puede variar
    send_invitation: bool = params.get("sendInvitation", True)
    message_invitation: Optional[str] = params.get("message")
    expiration_datetime_str: Optional[str] = params.get("expirationDateTime")
    password_sharing: Optional[str] = params.get("password")


    if (not item_id_or_path and not (list_id_or_name and list_item_id_param)) or not recipients_payload or not roles_payload:
        return _handle_graph_api_error(ValueError("Faltan parámetros: se necesita identificador de item, 'recipients' y 'roles'."), "add_item_permissions", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        url_action_invite: str
        log_item_description: str

        # Construir el cuerpo de la solicitud para la acción 'invite'
        body_invite_payload: Dict[str, Any] = {
            "recipients": recipients_payload, 
            "roles": roles_payload,
            "requireSignIn": require_signin,
            "sendInvitation": send_invitation
        }
        if message_invitation: body_invite_payload["message"] = message_invitation
        if expiration_datetime_str: body_invite_payload["expirationDateTime"] = expiration_datetime
        
        # (Continuación de la función sp_add_item_permissions)
        # El fragmento anterior que me mostraste terminaba aquí:
        # if expiration_datetime_str: body_invite_payload["expirationDateTime"] = expiration_datetime 

        # Determinar el endpoint y la descripción del log basado en si es DriveItem o ListItem
        if item_path_or_id: # Es un DriveItem
            target_drive_id = _get_drive_id(client, target_site_id, drive_id_or_name)
            # Usar el helper para obtener el ID del item si se pasó un path
            item_actual_id = _get_item_id_from_path_if_needed_sp(client, item_path_or_id, target_site_id, target_drive_id, params)
            if isinstance(item_actual_id, dict) and item_actual_id.get("status") == "error": # Chequeo si el helper devolvió error
                return item_actual_id 
            item_actual_id_str = str(item_actual_id) # Asegurar que es string para la URL
            
            url_invite = f"{_get_sp_item_endpoint_by_id(target_site_id, target_drive_id, item_actual_id_str)}/invite"
            log_item_desc = f"DriveItem ID '{item_actual_id_str}' (original: '{item_path_or_id}')"
        else: # Es un ListItem (list_id_or_name y list_item_id deben estar definidos por la validación anterior)
            url_invite = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_id}/lists/{list_id_or_name}/items/{list_item_id}/invite"
            log_item_desc = f"ListItem ID '{list_item_id}' en lista '{list_id_o_nombre}'"

        logger.info(f"Agregando/invitando permisos para {log_item_desc} con roles {roles_payload}")
        response = client.post(url_invite, scope=constants.GRAPH_SCOPE_SITES_FULLCONTROL_ALL, json=body_invite_payload) # Requiere permisos elevados
        # La respuesta de /invite es una colección de los permisos creados/actualizados
        return {"status": "success", "data": response.json().get("value", [])} 
    except Exception as e:
        # Usar el nombre de la función mapeada en el log de error
        return _handle_graph_api_error(e, "add_item_permissions", params) # Nombre mapeado: add_item_permissions

# Función mapeada: remove_item_permissions
def remove_item_permissions(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    item_path_or_id: Optional[str] = params.get("item_id_or_path")
    drive_id_or_name: Optional[str] = params.get("drive_id_or_name")
    list_id_or_name: Optional[str] = params.get("list_id_o_nombre")
    list_item_id: Optional[str] = params.get("list_item_id") # Renombrado en la función interna para evitar colisión con el param de la función externa
    permission_id: Optional[str] = params.get("permission_id") # ID del objeto de permiso a eliminar

    if (not item_path_or_id and not (list_id_or_name and list_item_id)) or not permission_id:
        return _handle_graph_api_error(ValueError("Faltan parámetros: 'item_id_or_path' (o 'list_id_o_nombre'+'list_item_id'), y 'permission_id' son requeridos."), "remove_item_permissions", params)

    try:
        target_site_id = _obtener_site_id_sp(client, params)
        url_delete_perm: str
        log_item_desc: str

        if item_path_or_id: # DriveItem
            target_drive_id = _get_drive_id(client, target_site_id, drive_id_or_name)
            item_actual_id = _get_item_id_from_path_if_needed_sp(client, item_path_or_id, target_site_id, target_drive_id, params)
            if isinstance(item_actual_id, dict) and item_actual_id.get("status") == "error": 
                return item_actual_id
            item_actual_id_str = str(item_actual_id)
            url_delete_perm = f"{_get_sp_item_endpoint_by_id(target_site_id, target_drive_id, item_actual_id_str)}/permissions/{permission_id}"
            log_item_desc = f"DriveItem ID '{item_actual_id_str}' (original: '{item_path_or_id}')"
        else: # ListItem
            url_delete_perm = f"{constants.GRAPH_API_BASE_URL}/sites/{target_site_id}/lists/{list_id_or_name}/items/{list_item_id}/permissions/{permission_id}"
            log_item_desc = f"ListItem ID '{list_item_id}' en lista '{list_id_o_nombre}'"
        
        logger.info(f"Eliminando permiso ID '{permission_id}' de {log_item_desc}")
        response = client.delete(url_delete_perm, scope=constants.GRAPH_SCOPE_SITES_FULLCONTROL_ALL)
        # DELETE exitoso devuelve 204 No Content
        return {"status": "success", "message": f"Permiso '{permission_id}' eliminado de {log_item_desc}.", "http_status": response.status_code}
    except Exception as e:
        return _handle_graph_api_error(e, "remove_item_permissions", params)

# =====================================================
# ==== ACCIONES DE MEMORIA USANDO LISTAS SHAREPOINT ====
# =====================================================
# Nombres de función deben coincidir con mapping_actions.py

def memory_ensure_list(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    logger.debug("Función 'memory_ensure_list' llamando a helper _ensure_memory_list_exists.")
    try:
        target_site_id = _obtener_site_id_sp(client, params) 
        success = _ensure_memory_list_exists(client, target_site_id) 
        if success:
            return {"status": "success", "message": f"Lista de memoria '{MEMORIA_LIST_NAME}' asegurada/creada en sitio '{target_site_id}'."}
        else:
            return {"status": "error", "message": f"No se pudo asegurar/crear lista de memoria '{MEMORIA_LIST_NAME}' en sitio '{target_site_id}'."}
    except Exception as e:
        return _handle_graph_api_error(e, "memory_ensure_list", params)

def memory_save(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    session_id: Optional[str] = params.get("session_id"); clave: Optional[str] = params.get("clave"); valor: Any = params.get("valor") 
    if not session_id or not clave or valor is None: 
        return _handle_graph_api_error(ValueError("'session_id', 'clave', 'valor' requeridos."),"memory_save", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        # Asegurar que la lista de memoria exista antes de intentar guardar
        ensure_params = params.copy() # Pasar params originales para que _obtener_site_id_sp funcione dentro
        ensure_result = memory_ensure_list(client, ensure_params)
        if ensure_result.get("status") != "success":
            return ensure_result # Propagar el error si no se pudo asegurar la lista
        
        valor_str = json.dumps(valor); filter_q = f"fields/SessionID eq '{session_id}' and fields/Clave eq '{clave}'"
        list_params = {"site_id": target_site_id, "lista_id_o_nombre": MEMORIA_LIST_NAME, 
                       "filter_query": filter_q, "top": 1, "select": "id,@odata.etag"}
        # Usar el nombre de función esperado por el mapping
        existing_items_response = list_list_items(client, list_params) 
        
        item_id, item_etag = None, None
        if existing_items_response.get("status") == "success":
            items_value = existing_items_response.get("data", {}).get("value", [])
            if items_value: 
                item_info = items_value[0]
                item_id = item_info.get("id")
                item_etag = item_info.get("@odata.etag")

        datos_campos_payload = {
            "SessionID": session_id, "Clave": clave, "Valor": valor_str,
            "Timestamp": _get_current_timestamp_iso()
        }
        if item_id: 
            update_params = {"site_id": target_site_id, "lista_id_o_nombre": MEMORIA_LIST_NAME, "item_id": item_id,
                             "nuevos_valores_campos": datos_campos_payload, "etag": item_etag}
            # Usar el nombre de función esperado por el mapping
            return update_list_item(client, update_params) 
        else: 
            add_params = {"site_id": target_site_id, "lista_id_o_nombre": MEMORIA_LIST_NAME, "datos_campos": datos_campos_payload}
            # Usar el nombre de función esperado por el mapping
            return add_list_item(client, add_params) 
    except Exception as e: 
        return _handle_graph_api_error(e, "memory_save", params)

def memory_get(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    session_id: Optional[str] = params.get("session_id"); clave: Optional[str] = params.get("clave") 
    if not session_id: 
        return _handle_graph_api_error(ValueError("'session_id' requerido."),"memory_get", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        # No es estrictamente necesario llamar a memory_ensure_list aquí, ya que si no existe no se encontrará nada.
        filter_parts = [f"fields/SessionID eq '{session_id}'"]
        if clave: filter_parts.append(f"fields/Clave eq '{clave}'")
        
        list_params = {"site_id": target_site_id, "lista_id_o_nombre": MEMORIA_LIST_NAME, 
                       "filter_query": " and ".join(filter_parts),
                       "select": "fields/Clave,fields/Valor,fields/Timestamp", "orderby": "fields/Timestamp desc"}
        # Usar el nombre de función esperado por el mapping
        items_response = list_list_items(client, list_params) 
        if items_response.get("status") != "success": return items_response

        retrieved_data: Any = {} if not clave else None
        items = items_response.get("data", {}).get("value", [])
        if not items:
            return {"status": "success", "data": retrieved_data, "message": "No data found for this session/key."}

        if clave: 
            valor_str = items[0].get("fields", {}).get("Valor")
            try: retrieved_data = json.loads(valor_str) if valor_str else None
            except json.JSONDecodeError: retrieved_data = valor_str 
        else: 
            for item in items:
                item_fields = item.get("fields", {}); current_clave = item_fields.get("Clave"); valor_str = item_fields.get("Valor")
                if current_clave and current_clave not in retrieved_data: 
                    try: retrieved_data[current_clave] = json.loads(valor_str) if valor_str else None
                    except json.JSONDecodeError: retrieved_data[current_clave] = valor_str
        return {"status": "success", "data": retrieved_data}
    except Exception as e: 
        return _handle_graph_api_error(e, "memory_get", params)

def memory_delete(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    session_id: Optional[str] = params.get("session_id"); clave: Optional[str] = params.get("clave") 
    if not session_id: 
        return _handle_graph_api_error(ValueError("'session_id' requerido."), "memory_delete", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        filter_parts = [f"fields/SessionID eq '{session_id}'"]
        log_action_detail = f"sesión '{session_id}'"
        if clave: 
            filter_parts.append(f"fields/Clave eq '{clave}'")
            log_action_detail = f"clave '{clave}' de sesión '{session_id}'"
        
        list_params = {"site_id": target_site_id, "lista_id_o_nombre": MEMORIA_LIST_NAME, 
                       "filter_query": " and ".join(filter_parts), "select": "id", 
                       "max_items_total": None } # Borrar todos los coincidentes
        # Usar el nombre de función esperado por el mapping
        items_to_delete_resp = list_list_items(client, list_params) 
        if items_to_delete_resp.get("status") != "success": return items_to_delete_resp
        
        items = items_to_delete_resp.get("data", {}).get("value", [])
        if not items:
            return {"status": "success", "message": f"No se encontró {log_action_detail} para eliminar."}

        deleted_count = 0; errors_on_delete = []
        for item in items:
            item_id = item.get("id")
            if item_id:
                del_params = {"site_id": target_site_id, "lista_id_o_nombre": MEMORIA_LIST_NAME, "item_id": item_id}
                # Usar el nombre de función esperado por el mapping
                del_response = delete_list_item(client, del_params) 
                if del_response.get("status") == "success": deleted_count += 1
                else: errors_on_delete.append(del_response.get("details", f"Error borrando item {item_id}"))
        
        if errors_on_delete: 
            return {"status": "partial_error", "message": f"{deleted_count} items de {log_action_detail} borrados, con errores.", "details": errors_on_delete}
        return {"status": "success", "message": f"Memoria para {log_action_detail} eliminada. {deleted_count} items borrados."}
    except Exception as e: 
        return _handle_graph_api_error(e, "memory_delete", params)

def memory_list_keys(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    session_id: Optional[str] = params.get("session_id")
    if not session_id: 
        return _handle_graph_api_error(ValueError("'session_id' requerido."), "memory_list_keys", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        list_params = {"site_id": target_site_id, "lista_id_o_nombre": MEMORIA_LIST_NAME, 
                       "filter_query": f"fields/SessionID eq '{session_id}'", 
                       "select": "fields/Clave", "max_items_total": None }
        # Usar el nombre de función esperado por el mapping
        items_response = list_list_items(client, list_params) 
        if items_response.get("status") != "success": return items_response
        keys = list(set(item.get("fields", {}).get("Clave") for item in items_response.get("data", {}).get("value", []) if item.get("fields", {}).get("Clave")))
        return {"status": "success", "data": keys}
    except Exception as e: 
        return _handle_graph_api_error(e, "memory_list_keys", params)

def memory_export_session(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Union[str, Dict[str, Any]]:
    session_id: Optional[str] = params.get("session_id"); export_format: str = params.get("format", "json").lower() 
    if not session_id: 
        return _handle_graph_api_error(ValueError("'session_id' requerido."), "memory_export_session", params)
    if export_format not in ["json", "csv"]: 
        return _handle_graph_api_error(ValueError("Formato debe ser 'json' o 'csv'."), "memory_export_session", params)
    
    export_params = {
        "site_id": params.get("site_id"), 
        "lista_id_o_nombre": MEMORIA_LIST_NAME,
        "format": export_format,
        "filter_query": f"fields/SessionID eq '{session_id}'",
        "select_fields": "SessionID,Clave,Valor,Timestamp" 
    }
    # Llamar a la función genérica sp_export_list_to_format (nombre interno)
    return sp_export_list_to_format(client, export_params) 

# ============================================
# ==== ACCIONES DE EXPORTACIÓN DE LISTAS (Genérica) ====
# ============================================
# Esta función es referenciada por memory_export_session.
# El mapping_actions.py no la lista explícitamente, así que su nombre con prefijo sp_ está bien.
# Si el mapping SÍ la tuviera como "export_list_to_format", se debería renombrar.
def sp_export_list_to_format(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Union[str, Dict[str, Any]]:
    lista_id_o_nombre: Optional[str] = params.get("lista_id_o_nombre"); export_format: str = params.get("format", "json").lower()
    filter_query: Optional[str] = params.get("filter_query"); select_fields: Optional[str] = params.get("select_fields") 
    max_items_total: Optional[int] = params.get('max_items_total')

    if not lista_id_o_nombre: 
        return _handle_graph_api_error(ValueError("'lista_id_o_nombre' requerido."), "sp_export_list_to_format", params)
    if export_format not in ["json", "csv"]: 
        return _handle_graph_api_error(ValueError("Formato no válido. Use 'json' o 'csv'."), "sp_export_list_to_format", params)
    try:
        target_site_id = _obtener_site_id_sp(client, params)
        list_items_params: Dict[str, Any] = {"site_id": target_site_id, "lista_id_o_nombre": lista_id_o_nombre, "max_items_total": max_items_total}
        if filter_query: list_items_params["filter_query"] = filter_query
        
        expand_val = "fields"
        select_val = None 
        if select_fields: 
            expand_val = f"fields(select={select_fields})"
            select_val = "id,@odata.etag" 
        
        list_items_params["expand"] = expand_val
        if select_val : list_items_params["select"] = select_val
            
        logger.info(f"Exportando lista '{lista_id_o_nombre}' del sitio '{target_site_id}' a formato '{export_format}'")
        # Usar el nombre de función esperado por el mapping
        items_response = list_list_items(client, list_items_params) 
        if items_response.get("status") != "success": return items_response

        items_data = items_response.get("data", {}).get("value", [])
        processed_items = []
        for item in items_data:
            fields = item.get("fields", {})
            fields["_ListItemID_"] = item.get("id"); fields["_ListItemETag_"] = item.get("@odata.etag") 
            processed_items.append(fields)
        if not processed_items: 
            return {"status": "success", "data": []} if export_format == "json" else ""
        if export_format == "json": 
            return {"status": "success", "data": processed_items}
        
        output = StringIO(); all_keys = set()
        for item_fields in processed_items: all_keys.update(item_fields.keys())
        fieldnames_ordered = sorted(list(all_keys))
        if "_ListItemID_" in fieldnames_ordered: fieldnames_ordered.insert(0, fieldnames_ordered.pop(fieldnames_ordered.index("_ListItemID_")))
        if "_ListItemETag_" in fieldnames_ordered and "_ListItemETag_" in all_keys:
            idx = fieldnames_ordered.index("_ListItemETag_"); 
            if idx != -1 : fieldnames_ordered.insert(1, fieldnames_ordered.pop(idx))
        writer = csv.DictWriter(output, fieldnames=fieldnames_ordered, extrasaction='ignore', quoting=csv.QUOTE_ALL)
        writer.writeheader(); writer.writerows(processed_items)
        return output.getvalue()
    except Exception as e: 
        return _handle_graph_api_error(e, "sp_export_list_to_format", params)

# --- FIN DEL MÓDULO actions/sharepoint_actions.py ---