# MyHttpTrigger/actions/onedrive_actions.py
import logging
import requests # Para tipos de excepción y llamadas directas a uploadUrl de sesión
import json
from typing import Dict, List, Optional, Union, Any

# Importar el cliente autenticado y las constantes
from shared.helpers.http_client import AuthenticatedHttpClient
from shared import constants # GRAPH_API_BASE_URL, GRAPH_SCOPE, etc.

logger = logging.getLogger(__name__)

# Constante local para timeout si no está en constants.py
DEFAULT_CHUNK_UPLOAD_TIMEOUT_SECONDS = getattr(constants, 'DEFAULT_API_TIMEOUT', 120)


# ---- Helpers Locales para Endpoints de OneDrive (/me/drive) ----
def _get_od_me_drive_base_endpoint() -> str:
    """Devuelve el endpoint base para el drive principal del usuario: /me/drive"""
    return f"{constants.GRAPH_API_BASE_URL}/me/drive"

def _get_od_me_item_by_path_endpoint(relative_path: str) -> str:
    """Devuelve el endpoint para un item en /me/drive por su ruta relativa a la raíz."""
    drive_endpoint = _get_od_me_drive_base_endpoint()
    safe_path = relative_path.strip()
    if not safe_path or safe_path == '/': # Raíz del drive
        return f"{drive_endpoint}/root"
    
    if safe_path.startswith('/'):
        safe_path = safe_path[1:]
    return f"{drive_endpoint}/root:/{safe_path}"

def _get_od_me_item_by_id_endpoint(item_id: str) -> str:
    """Devuelve el endpoint para un item en /me/drive por su ID."""
    drive_endpoint = _get_od_me_drive_base_endpoint()
    return f"{drive_endpoint}/items/{item_id}"


# --- Helper para manejar errores de OneDrive API de forma centralizada ---
def _handle_onedrive_api_error(e: Exception, action_name: str, params_for_log: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    log_message = f"Error en OneDrive action '{action_name}'"
    if params_for_log:
        safe_params = {k: v for k, v in params_for_log.items() if k not in ['contenido_bytes', 'password']}
        log_message += f" con params: {safe_params}"
    log_message += f": {type(e).__name__} - {e}"
    
    logger.error(log_message, exc_info=True)
    
    details = str(e)
    status_code = 500
    error_code_graph = None

    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
        status_code = e.response.status_code
        try:
            error_data = e.response.json()
            details = error_data.get("error", {}).get("message", e.response.text)
            error_code_graph = error_data.get("error", {}).get("code")
        except json.JSONDecodeError:
            details = e.response.text
            
    return {
        "status": "error",
        "action": action_name,
        "message": f"Error en {action_name}: {type(e).__name__}",
        "http_status": status_code,
        "details": details,
        "graph_error_code": error_code_graph
    }

# --- Helper para obtener ID de item si se provee path ---
# Definición interna para que las funciones de este módulo la usen.
def _internal_onedrive_get_item_metadata(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    item_path_or_id: Optional[str] = params.get("item_id_o_nombre_con_ruta")
    select: Optional[str] = params.get("select")
    expand: Optional[str] = params.get("expand")

    if not item_path_or_id:
        return _handle_onedrive_api_error(ValueError("'item_id_o_nombre_con_ruta' es requerido."), "_internal_onedrive_get_item_metadata", params)
    try:
        if "/" in item_path_or_id or ("." in item_path_or_id and not item_path_or_id.startswith("driveItem_") and len(item_path_or_id) < 60):
            item_endpoint = _get_od_me_item_by_path_endpoint(item_path_or_id)
        else: 
            item_endpoint = _get_od_me_item_by_id_endpoint(item_path_or_id)

        query_api_params: Dict[str, Any] = {}
        if select: query_api_params['$select'] = select
        if expand: query_api_params['$expand'] = expand
        
        logger.info(f"Obteniendo metadatos OneDrive /me (interno): '{item_path_or_id}' desde endpoint '{item_endpoint}'")
        response = client.get(item_endpoint, scope=constants.GRAPH_SCOPE_FILES_READ_ALL, params=query_api_params if query_api_params else None)
        return {"status": "success", "data": response.json()}
    except Exception as e:
        return _handle_onedrive_api_error(e, "_internal_onedrive_get_item_metadata", params)


def _get_item_id_from_path_if_needed(
    client: AuthenticatedHttpClient, 
    item_path_or_id: str,
    params_for_metadata: Optional[Dict[str, Any]] = None 
) -> Union[str, Dict[str, Any]]:
    is_path = "/" in item_path_or_id or \
              ("." in item_path_or_id and not item_path_or_id.startswith("driveItem_") and len(item_path_or_id) < 70) or \
              (not item_path_or_id.startswith("driveItem_") and len(item_path_or_id) < 70 and '.' not in item_path_or_id)


    if not is_path and (item_path_or_id.startswith("driveItem_") or len(item_path_or_id) > 60) : 
        logger.debug(f"Asumiendo que '{item_path_or_id}' ya es un ID de item OneDrive.")
        return item_path_or_id

    logger.debug(f"'{item_path_or_id}' parece un path en OneDrive. Intentando obtener su ID.")
    metadata_params = {"item_id_o_nombre_con_ruta": item_path_or_id, "select": "id,name"}
    
    response = _internal_onedrive_get_item_metadata(client, metadata_params) 
    if response.get("status") == "success" and response.get("data", {}).get("id"):
        item_id = response["data"]["id"]
        logger.info(f"ID obtenido para path OneDrive '{item_path_or_id}': {item_id}")
        return item_id
    else:
        error_msg = f"No se pudo obtener el ID para el path/item OneDrive '{item_path_or_id}'."
        logger.error(error_msg + f" Detalles: {response}")
        return response if isinstance(response, dict) and response.get("status") == "error" else \
               {"status": "error", "message": error_msg, "details": str(response)}


# --- Helper común para paginación ---
def _onedrive_paged_request(
    client: AuthenticatedHttpClient,
    url_base: str,
    scope: str,
    params: Dict[str, Any], 
    query_api_params_initial: Dict[str, Any],
    max_items_total: int,
    action_name_for_log: str # Nombre de la función pública para logging
) -> Dict[str, Any]:
    all_items: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0
    max_pages = 30 
    
    top_per_page = query_api_params_initial.get('$top', 50)

    logger.info(f"Iniciando solicitud paginada para '{action_name_for_log}' desde '{url_base.split('?')[0]}...'. "
                f"Max total: {max_items_total}, por página: {top_per_page}, max_páginas: {max_pages}")
    try:
        while current_url and len(all_items) < max_items_total and page_count < max_pages:
            page_count += 1
            is_first_call = (current_url == url_base and page_count == 1)
            
            logger.debug(f"Página {page_count} para '{action_name_for_log}': GET {current_url.split('?')[0]}...")
            response = client.get(
                url=current_url, 
                scope=scope, 
                params=query_api_params_initial if is_first_call else None
            )
            response_data = response.json()
            
            page_items = response_data.get('value', [])
            if not isinstance(page_items, list):
                logger.warning(f"Respuesta inesperada en paginación para '{action_name_for_log}', 'value' no es una lista: {response_data}")
                break
            
            for item in page_items:
                if len(all_items) < max_items_total:
                    all_items.append(item)
                else:
                    break 
            
            current_url = response_data.get('@odata.nextLink')
            if not current_url or len(all_items) >= max_items_total:
                break 
        
        logger.info(f"'{action_name_for_log}' recuperó {len(all_items)} items en {page_count} páginas.")
        return {"status": "success", "data": all_items, "total_retrieved": len(all_items), "pages_processed": page_count}
    except Exception as e:
        return _handle_onedrive_api_error(e, action_name_for_log, params)


# ---- FUNCIONES DE ACCIÓN PARA ONEDRIVE (/me/drive) ----
# Nombres de función deben coincidir con el mapping_actions.py (ej. list_items, get_item)

def list_items(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    ruta_param: str = params.get("ruta", "/") 
    top_per_page: int = min(int(params.get("top_per_page", 50)), 200)
    max_items_total: int = int(params.get("max_items_total", 100))
    select: Optional[str] = params.get("select")
    filter_query: Optional[str] = params.get("filter_query")
    order_by: Optional[str] = params.get("order_by")

    try:
        is_likely_id = not ("/" in ruta_param) and len(ruta_param) > 30 and not ("." in ruta_param)
        
        if is_likely_id:
            logger.debug(f"Asumiendo que ruta '{ruta_param}' es un ID de carpeta para listar items.")
            item_endpoint_base = _get_od_me_item_by_id_endpoint(ruta_param)
        else:
            item_endpoint_base = _get_od_me_item_by_path_endpoint(ruta_param)

        url_base = f"{item_endpoint_base}/children"
        
        query_api_params: Dict[str, Any] = {'$top': top_per_page}
        if select: query_api_params['$select'] = select
        if filter_query: query_api_params['$filter'] = filter_query
        if order_by: query_api_params['$orderby'] = order_by
        
        return _onedrive_paged_request(client, url_base, constants.GRAPH_SCOPE_FILES_READ_ALL, params, query_api_params, max_items_total, "list_items")
    except Exception as e: 
        return _handle_onedrive_api_error(e, "list_items (setup)", params)

def get_item(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    # Esta función es la que espera el mapping. Llama a la función interna más descriptiva.
    logger.debug("Action 'get_item' (OneDrive) llamando a lógica interna de metadatos.")
    return _internal_onedrive_get_item_metadata(client, params)

def upload_file(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    nombre_archivo: Optional[str] = params.get("nombre_archivo")
    contenido_bytes: Optional[bytes] = params.get("contenido_bytes")
    ruta_destino_relativa: str = params.get("ruta_destino_relativa", "/") 
    conflict_behavior: str = params.get("conflict_behavior", "rename")

    if not nombre_archivo or contenido_bytes is None:
        return _handle_onedrive_api_error(ValueError("'nombre_archivo' y 'contenido_bytes' son requeridos."),"upload_file", params)
    if not isinstance(contenido_bytes, bytes):
        return _handle_onedrive_api_error(ValueError("'contenido_bytes' debe ser de tipo bytes."), "upload_file", params)

    try:
        clean_folder_path = ruta_destino_relativa.strip('/')
        target_file_path_for_api = f"{nombre_archivo}" if not clean_folder_path else f"{clean_folder_path}/{nombre_archivo}"
        item_endpoint_for_upload_base = _get_od_me_item_by_path_endpoint(target_file_path_for_api)
        
        file_size_bytes = len(contenido_bytes)
        file_size_mb = file_size_bytes / (1024.0 * 1024.0)
        logger.info(f"Subiendo a OneDrive /me: path API 'root:/{target_file_path_for_api}' ({file_size_mb:.2f} MB), conflict: '{conflict_behavior}'")

        if file_size_mb > 4.0: # Sesión de carga
            logger.info("Archivo > 4MB. Iniciando sesión de carga para OneDrive.")
            create_session_url = f"{item_endpoint_for_upload_base}:/createUploadSession"
            session_body = {"item": {"@microsoft.graph.conflictBehavior": conflict_behavior, "name": nombre_archivo }}
            response_session = client.post(create_session_url, scope=constants.GRAPH_SCOPE_FILES_READ_WRITE_ALL, json=session_body)
            session_info = response_session.json()
            upload_url_from_session = session_info.get("uploadUrl")
            if not upload_url_from_session: raise ValueError("No se pudo obtener 'uploadUrl' de la sesión.")
            logger.info(f"Sesión de carga OD creada. URL (preview): {upload_url_from_session.split('?')[0]}...")
            chunk_size = 5 * 1024 * 1024; start_byte = 0
            final_item_metadata: Optional[Dict[str, Any]] = None
            while start_byte < file_size_bytes:
                end_byte = min(start_byte + chunk_size - 1, file_size_bytes - 1)
                current_chunk_data = contenido_bytes[start_byte : end_byte + 1]
                content_range_header = f"bytes {start_byte}-{end_byte}/{file_size_bytes}"
                chunk_upload_timeout = max(DEFAULT_CHUNK_UPLOAD_TIMEOUT_SECONDS, int(len(current_chunk_data) / (50 * 1024)) + 10)
                chunk_headers = {'Content-Length': str(len(current_chunk_data)), 'Content-Range': content_range_header}
                logger.debug(f"Subiendo chunk OD: {content_range_header}, timeout: {chunk_upload_timeout}s")
                chunk_response = requests.put(upload_url_from_session, headers=chunk_headers, data=current_chunk_data, timeout=chunk_upload_timeout)
                chunk_response.raise_for_status() 
                start_byte = end_byte + 1
                if chunk_response.content: 
                    try: 
                        response_json = chunk_response.json()
                        if chunk_response.status_code in [200, 201] and response_json.get("id"): final_item_metadata = response_json; break
                        elif chunk_response.status_code == 202 : logger.debug(f"Chunk aceptado. Próximo byte: {response_json.get('nextExpectedRanges')}")
                    except json.JSONDecodeError: logger.warning(f"Respuesta chunk OD (status {chunk_response.status_code}) no JSON: {chunk_response.text[:200]}")
                elif start_byte >= file_size_bytes: break
            if not final_item_metadata: raise ValueError(f"Subida grande OD finalizada pero sin metadata. Último status: {chunk_response.status_code if 'chunk_response' in locals() else 'N/A'}")
            return {"status": "success", "data": final_item_metadata, "message": "Archivo subido con sesión."}
        else: # Subida simple
            logger.info("Archivo <= 4MB. Usando subida simple para OneDrive.")
            url_put_simple = f"{item_endpoint_for_upload_base}:/content"
            query_api_params_put = {"@microsoft.graph.conflictBehavior": conflict_behavior}
            custom_headers_put = {'Content-Type': 'application/octet-stream'}
            response = client.put(url=url_put_simple, scope=constants.GRAPH_SCOPE_FILES_READ_WRITE_ALL, params=query_api_params_put, data=contenido_bytes, headers=custom_headers_put)
            return {"status": "success", "data": response.json(), "message": "Archivo subido (simple)."}
    except Exception as e:
        return _handle_onedrive_api_error(e, "upload_file", params)

def download_file(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Union[bytes, Dict[str, Any]]:
    item_path_or_id: Optional[str] = params.get("item_id_o_nombre_con_ruta")
    if not item_path_or_id:
        return _handle_onedrive_api_error(ValueError("'item_id_o_nombre_con_ruta' es requerido."), "download_file", params)
    try:
        if "/" in item_path_or_id or ("." in item_path_or_id and not item_path_or_id.startswith("driveItem_") and len(item_path_or_id) < 70): # Ajuste heurística
            item_endpoint_base = _get_od_me_item_by_path_endpoint(item_path_or_id)
        else:
            item_endpoint_base = _get_od_me_item_by_id_endpoint(item_path_or_id)
        url = f"{item_endpoint_base}/content"
        logger.info(f"Descargando archivo OneDrive /me: '{item_path_or_id}'")
        response = client.get(url, scope=constants.GRAPH_SCOPE_FILES_READ_ALL, stream=True)
        file_bytes = response.content
        logger.info(f"Archivo OneDrive '{item_path_or_id}' descargado ({len(file_bytes)} bytes).")
        return file_bytes
    except Exception as e:
        return _handle_onedrive_api_error(e, "download_file", params)

def delete_item(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    item_path_or_id: Optional[str] = params.get("item_id_o_nombre_con_ruta")
    if not item_path_or_id:
        return _handle_onedrive_api_error(ValueError("'item_id_o_nombre_con_ruta' es requerido."), "delete_item", params)
    try:
        resolved_item_id = _get_item_id_from_path_if_needed(client, item_path_or_id, params)
        if isinstance(resolved_item_id, dict) and resolved_item_id.get("status") == "error":
            return resolved_item_id
        item_endpoint_for_delete = _get_od_me_item_by_id_endpoint(str(resolved_item_id))
        logger.info(f"Eliminando item OneDrive /me: ID '{resolved_item_id}' (original: '{item_path_or_id}')")
        response = client.delete(item_endpoint_for_delete, scope=constants.GRAPH_SCOPE_FILES_READ_WRITE_ALL)
        return {"status": "success", "message": f"Elemento '{item_path_or_id}' eliminado.", "http_status": response.status_code}
    except Exception as e:
        return _handle_onedrive_api_error(e, "delete_item", params)

def create_folder(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    nombre_carpeta: Optional[str] = params.get("nombre_carpeta")
    ruta_padre_relativa: str = params.get("ruta_padre_relativa", "/")
    conflict_behavior: str = params.get("conflict_behavior", "fail")

    if not nombre_carpeta:
        return _handle_onedrive_api_error(ValueError("'nombre_carpeta' es requerido."), "create_folder", params)
    try:
        if ruta_padre_relativa == "/":
            parent_item_endpoint = _get_od_me_item_by_path_endpoint("/")
        else:
            resolved_parent_id = _get_item_id_from_path_if_needed(client, ruta_padre_relativa, params)
            if isinstance(resolved_parent_id, dict) and resolved_parent_id.get("status") == "error":
                return resolved_parent_id
            parent_item_endpoint = _get_od_me_item_by_id_endpoint(str(resolved_parent_id))

        url = f"{parent_item_endpoint}/children"
        body = {"name": nombre_carpeta, "folder": {}, "@microsoft.graph.conflictBehavior": conflict_behavior}
        logger.info(f"Creando carpeta OneDrive /me: '{nombre_carpeta}' en ruta padre '{ruta_padre_relativa}'")
        response = client.post(url, scope=constants.GRAPH_SCOPE_FILES_READ_WRITE_ALL, json=body)
        return {"status": "success", "data": response.json(), "message": f"Carpeta '{nombre_carpeta}' creada."}
    except Exception as e:
        return _handle_onedrive_api_error(e, "create_folder", params)

def move_item(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    item_path_or_id_origen: Optional[str] = params.get("item_id_o_nombre_con_ruta_origen")
    parent_reference_param: Optional[Dict[str, str]] = params.get("parent_reference") 
    nuevo_nombre: Optional[str] = params.get("nuevo_nombre")

    if not item_path_or_id_origen:
        return _handle_onedrive_api_error(ValueError("'item_id_o_nombre_con_ruta_origen' es requerido."), "move_item", params)
    if not parent_reference_param or not isinstance(parent_reference_param, dict):
        return _handle_onedrive_api_error(ValueError("'parent_reference' (dict con 'id' o 'path') requerido."), "move_item", params)
    
    parent_id = parent_reference_param.get("id")
    parent_path = parent_reference_param.get("path")
    if not parent_id and not parent_path:
        return _handle_onedrive_api_error(ValueError("'parent_reference' debe tener 'id' o 'path'."), "move_item", params)
    try:
        resolved_item_id_origen = _get_item_id_from_path_if_needed(client, item_path_or_id_origen, params)
        if isinstance(resolved_item_id_origen, dict) and resolved_item_id_origen.get("status") == "error":
            return resolved_item_id_origen
        item_origen_endpoint_for_patch = _get_od_me_item_by_id_endpoint(str(resolved_item_id_origen))
        body: Dict[str, Any] = {"parentReference": {}}
        if parent_id: body["parentReference"]["id"] = parent_id
        elif parent_path:
            if not parent_path.startswith("/drive/root:"): # Path para parentReference en OneDrive
                fixed_parent_path = f"/drive/root:{parent_path.lstrip('/')}" if parent_path != "/" else "/drive/root:"
                logger.warning(f"Path de parent_reference '{parent_path}' ajustado a '{fixed_parent_path}'.")
                body["parentReference"]["path"] = fixed_parent_path
            else:
                body["parentReference"]["path"] = parent_path

        if nuevo_nombre: body["name"] = nuevo_nombre
        logger.info(f"Moviendo OneDrive /me item ID '{resolved_item_id_origen}' a '{parent_reference_param}'. Nuevo nombre: '{body.get('name')}'")
        response = client.patch(item_origen_endpoint_for_patch, scope=constants.GRAPH_SCOPE_FILES_READ_WRITE_ALL, json=body)
        return {"status": "success", "data": response.json(), "message": "Elemento movido/renombrado."}
    except Exception as e:
        return _handle_onedrive_api_error(e, "move_item", params)

def copy_item(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    item_path_or_id_origen: Optional[str] = params.get("item_id_o_nombre_con_ruta_origen")
    parent_reference_param: Optional[Dict[str, str]] = params.get("parent_reference")
    nuevo_nombre_copia: Optional[str] = params.get("nuevo_nombre_copia")

    if not item_path_or_id_origen:
        return _handle_onedrive_api_error(ValueError("'item_id_o_nombre_con_ruta_origen' es requerido."), "copy_item", params)
    if not parent_reference_param or not isinstance(parent_reference_param, dict):
         return _handle_onedrive_api_error(ValueError("'parent_reference' (dict con 'id' o 'path') requerido."), "copy_item", params)
    parent_id = parent_reference_param.get("id")
    parent_path = parent_reference_param.get("path")
    if not parent_id and not parent_path:
        return _handle_onedrive_api_error(ValueError("'parent_reference' debe tener 'id' o 'path'."), "copy_item", params)
    try:
        resolved_item_id_origen = _get_item_id_from_path_if_needed(client, item_path_or_id_origen, params)
        if isinstance(resolved_item_id_origen, dict) and resolved_item_id_origen.get("status") == "error":
            return resolved_item_id_origen
        item_origen_endpoint_for_copy = _get_od_me_item_by_id_endpoint(str(resolved_item_id_origen))
        url_copy = f"{item_origen_endpoint_for_copy}/copy"
        body: Dict[str, Any] = {"parentReference": {}}
        if parent_id: body["parentReference"]["id"] = parent_id
        elif parent_path:
            if not parent_path.startswith("/drive/root:"):
                fixed_parent_path = f"/drive/root:{parent_path.lstrip('/')}" if parent_path != "/" else "/drive/root:"
                logger.warning(f"Path de parent_reference para copia '{parent_path}' ajustado a '{fixed_parent_path}'.")
                body["parentReference"]["path"] = fixed_parent_path
            else:
                body["parentReference"]["path"] = parent_path
        if nuevo_nombre_copia: body["name"] = nuevo_nombre_copia
        logger.info(f"Iniciando copia OneDrive /me item ID '{resolved_item_id_origen}' a '{parent_reference_param}'. Nuevo nombre: '{body.get('name')}'")
        response = client.post(url_copy, scope=constants.GRAPH_SCOPE_FILES_READ_WRITE_ALL, json=body)
        monitor_url = response.headers.get('Location')
        if response.status_code == 202 and monitor_url:
            return {"status": "pending", "message": "Solicitud de copia aceptada.", "monitor_url": monitor_url, "data": response.text, "http_status": 202}
        logger.warning(f"Respuesta de copia OD inesperada. Status: {response.status_code}, Headers: {response.headers}")
        return {"status": "error", "message": "Respuesta inesperada o incompleta al iniciar copia.", "details": response.text, "http_status": response.status_code}
    except Exception as e:
        return _handle_onedrive_api_error(e, "copy_item", params)

# onedrive_update_item_metadata está mapeada a 'update_item_metadata' en el archivo original
# Aseguramos que el nombre de la función sea 'update_item_metadata'
def update_item_metadata(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: 
    item_path_or_id: Optional[str] = params.get("item_id_o_nombre_con_ruta")
    nuevos_valores: Optional[Dict[str, Any]] = params.get("nuevos_valores") 
    if not item_path_or_id:
        return _handle_onedrive_api_error(ValueError("'item_id_o_nombre_con_ruta' es requerido."), "update_item_metadata", params)
    if not nuevos_valores or not isinstance(nuevos_valores, dict):
        return _handle_onedrive_api_error(ValueError("'nuevos_valores' (dict) es requerido."), "update_item_metadata", params)
    try:
        resolved_item_id = _get_item_id_from_path_if_needed(client, item_path_or_id, params)
        if isinstance(resolved_item_id, dict) and resolved_item_id.get("status") == "error":
            return resolved_item_id
        item_endpoint_for_update = _get_od_me_item_by_id_endpoint(str(resolved_item_id))
        custom_headers = {}
        etag = nuevos_valores.pop('@odata.etag', params.get('etag')) 
        if etag: custom_headers['If-Match'] = etag
        logger.info(f"Actualizando metadatos OneDrive /me: ID '{resolved_item_id}' (original: '{item_path_or_id}')")
        response = client.patch(item_endpoint_for_update, scope=constants.GRAPH_SCOPE_FILES_READ_WRITE_ALL, json=nuevos_valores, headers=custom_headers)
        return {"status": "success", "data": response.json(), "message": "Metadatos actualizados."}
    except Exception as e:
        return _handle_onedrive_api_error(e, "update_item_metadata", params)

# --- Nuevas Funciones Añadidas según mapping_actions.py ---

def search_items(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    query_text: Optional[str] = params.get("query_text")
    top_per_page: int = min(int(params.get("top_per_page", 50)), 200) 
    max_items_total: int = int(params.get("max_items_total", 100))
    select: Optional[str] = params.get("select")
    
    if not query_text:
        return _handle_onedrive_api_error(ValueError("'query_text' es requerido."), "search_items", params)

    search_scope_path: str = params.get("search_scope_path", "") 
    
    if search_scope_path and search_scope_path != "/":
        base_item_endpoint = _get_od_me_item_by_path_endpoint(search_scope_path)
    else: 
        base_item_endpoint = _get_od_me_drive_base_endpoint()
        
    url_base = f"{base_item_endpoint}/search(q='{query_text}')" # El query_text no debe estar pre-encodeado aquí
    
    query_api_params: Dict[str, Any] = {'$top': top_per_page}
    if select: query_api_params['$select'] = select
    
    logger.info(f"Buscando en OneDrive /me (Scope: '{search_scope_path or 'todo el drive'}', Query: '{query_text}')")
    all_found_resources: List[Dict[str, Any]] = []
    current_url_search: Optional[str] = url_base
    page_count_search = 0
    max_pages_search = 10 

    try:
        while current_url_search and len(all_found_resources) < max_items_total and page_count_search < max_pages_search:
            page_count_search += 1
            is_first_search_call = (current_url_search == url_base and page_count_search == 1)
            
            logger.debug(f"Página {page_count_search} para search_items: GET {current_url_search.split('?')[0]}...")
            # El q='{text}' ya está en la URL base, no se pasa en params para /search
            # Los params OData como $top, $select SÍ se pasan en el diccionario de params
            response = client.get(
                url=current_url_search,
                scope=constants.GRAPH_SCOPE_FILES_READ_ALL,
                params=query_api_params if is_first_search_call else None 
            )
            search_page_data = response.json()
            
            items_from_page: List[Dict[str, Any]] = []
            raw_value = search_page_data.get('value', [])

            if isinstance(raw_value, list):
                for hit_or_container in raw_value:
                    if 'hitsContainers' in hit_or_container: 
                        for container in hit_or_container.get('hitsContainers', []):
                            for hit in container.get('hits', []):
                                if 'resource' in hit: items_from_page.append(hit['resource'])
                    elif 'resource' in hit_or_container: 
                        items_from_page.append(hit_or_container['resource'])
                    elif 'id' in hit_or_container : 
                        items_from_page.append(hit_or_container)

            for item_res in items_from_page:
                if len(all_found_resources) < max_items_total:
                    all_found_resources.append(item_res)
                else: break
            
            current_url_search = search_page_data.get('@odata.nextLink')
            if not current_url_search or len(all_found_resources) >= max_items_total: break
        
        logger.info(f"Búsqueda OneDrive encontró {len(all_found_resources)} items en {page_count_search} páginas.")
        return {"status": "success", "data": all_found_resources, "total_retrieved": len(all_found_resources), "pages_processed": page_count_search}
    except Exception as e:
        return _handle_onedrive_api_error(e, "search_items", params)

def get_sharing_link(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    item_path_or_id: Optional[str] = params.get("item_id_o_nombre_con_ruta")
    link_type: str = params.get("type", "view") 
    scope: str = params.get("scope", "organization") 
    password: Optional[str] = params.get("password") 
    expiration_datetime: Optional[str] = params.get("expirationDateTime") 

    if not item_path_or_id:
        return _handle_onedrive_api_error(ValueError("'item_id_o_nombre_con_ruta' es requerido."), "get_sharing_link", params)
    try:
        resolved_item_id = _get_item_id_from_path_if_needed(client, item_path_or_id, params)
        if isinstance(resolved_item_id, dict) and resolved_item_id.get("status") == "error":
            return resolved_item_id
        
        item_endpoint_for_link = _get_od_me_item_by_id_endpoint(str(resolved_item_id))
        url_create_link = f"{item_endpoint_for_link}/createLink"
        
        body: Dict[str, Any] = {"type": link_type, "scope": scope}
        if password: body["password"] = password
        if expiration_datetime: body["expirationDateTime"] = expiration_datetime
        
        logger.info(f"Creando/obteniendo enlace para OneDrive item ID '{resolved_item_id}' (original: '{item_path_or_id}')")
        response = client.post(url_create_link, scope=constants.GRAPH_SCOPE_FILES_READ_WRITE_ALL, json=body) 
        return {"status": "success", "data": response.json()} 
    except Exception as e:
        return _handle_onedrive_api_error(e, "get_sharing_link", params)

# --- FIN DEL MÓDULO actions/onedrive_actions.py ---