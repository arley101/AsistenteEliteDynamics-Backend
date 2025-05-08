# MyHttpTrigger/actions/onedrive_actions.py
import logging
import requests # Para tipos de excepción y llamadas directas a uploadUrl de sesión
import os
import json
from typing import Dict, List, Optional, Union, Any

# Importar helper y constantes
try:
    from ..shared.helpers.http_client import hacer_llamada_api
    from ..shared.constants import BASE_URL, GRAPH_API_DEFAULT_TIMEOUT, APP_NAME
except ImportError as e:
    logging.critical(f"Error CRÍTICO importando dependencias compartidas en OneDrive: {e}.", exc_info=True)
    BASE_URL = "https://graph.microsoft.com/v1.0"
    GRAPH_API_DEFAULT_TIMEOUT = 45
    APP_NAME = "EliteDynamicsPro" # Fallback
    raise ImportError(f"No se pudo importar 'hacer_llamada_api' o constantes: {e}") from e

logger = logging.getLogger(f"{APP_NAME}.actions.onedrive")

# ---- Helpers Locales para Endpoints de OneDrive (/me/drive) ----
def _get_od_me_drive_endpoint() -> str:
    """Devuelve el endpoint base para el drive principal del usuario (/me/drive)."""
    return f"{BASE_URL}/me/drive"

def _get_od_me_item_path_endpoint(ruta_relativa: str) -> str:
    """
    Construye la URL para un item específico por path relativo a la raíz de /me/drive.
    Ejemplos de ruta_relativa: "/", "/MiCarpeta", "/MiCarpeta/archivo.txt"
    """
    drive_endpoint = _get_od_me_drive_endpoint()
    safe_path = ruta_relativa.strip()

    if not safe_path or safe_path == '/':
        return f"{drive_endpoint}/root"
    
    # Asegurar que el path relativo para /root:/... no empiece con '/'
    if safe_path.startswith('/'):
        safe_path = safe_path[1:]
        
    # Escapar caracteres especiales si es necesario para la URL
    # from urllib.parse import quote
    # safe_path_encoded = quote(safe_path)
    # return f"{drive_endpoint}/root:/{safe_path_encoded}" 
    # Por ahora, asumimos que el path no necesita escaping complejo
    return f"{drive_endpoint}/root:/{safe_path}"

def _get_me_drive_id(headers: Dict[str, str]) -> str:
    """Obtiene el ID del drive principal del usuario (/me/drive). Cachea el resultado."""
    # Simple cache en memoria (podría mejorarse si fuera una clase)
    if not hasattr(_get_me_drive_id, "cached_drive_id"):
         _get_me_drive_id.cached_drive_id = None # type: ignore

    if _get_me_drive_id.cached_drive_id: # type: ignore
        return _get_me_drive_id.cached_drive_id # type: ignore

    drive_endpoint = _get_od_me_drive_endpoint()
    url = f"{drive_endpoint}?$select=id"
    try:
        logger.debug(f"Obteniendo Drive ID para /me/drive: GET {url}")
        drive_data = hacer_llamada_api("GET", url, headers, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        actual_drive_id = drive_data.get('id') if isinstance(drive_data, dict) else None
        if not actual_drive_id: raise ValueError("Respuesta inválida, no se pudo obtener 'id' del drive /me.")
        logger.info(f"Drive ID /me/drive obtenido: {actual_drive_id}")
        _get_me_drive_id.cached_drive_id = actual_drive_id # type: ignore Cachear
        return actual_drive_id
    except Exception as e:
        logger.error(f"Error API obteniendo Drive ID para /me/drive: {e}", exc_info=True)
        raise Exception(f"Error obteniendo Drive ID para /me/drive: {e}") from e


# ---- FUNCIONES DE ACCIÓN PARA ONEDRIVE (/me/drive) ----

def listar_archivos(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    ruta: str = parametros.get("ruta", "/")
    top_per_page: int = min(int(parametros.get("top_per_page", 25)), 200)
    max_items_total: int = int(parametros.get("max_items_total", 100))
    select: Optional[str] = parametros.get("select")
    filter_query: Optional[str] = parametros.get("filter_query")
    order_by: Optional[str] = parametros.get("order_by")

    item_endpoint = _get_od_me_item_path_endpoint(ruta)
    url_base = f"{item_endpoint}/children"
    
    query_params: Dict[str, Any] = {'$top': top_per_page}
    if select: query_params['$select'] = select
    if filter_query: query_params['$filter'] = filter_query
    if order_by: query_params['$orderby'] = order_by

    all_items: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0
    
    logger.info(f"Listando OneDrive /me, ruta '{ruta}' (max: {max_items_total}, pág: {top_per_page})")

    try:
        while current_url and len(all_items) < max_items_total:
            page_count += 1
            params_for_call = query_params if current_url == url_base and page_count == 1 else None
            logger.debug(f" Obteniendo página {page_count} de items OD desde: {current_url}")
            response_data = hacer_llamada_api("GET", current_url, headers, params=params_for_call, timeout=GRAPH_API_DEFAULT_TIMEOUT)
            if response_data and isinstance(response_data, dict) and 'value' in response_data:
                items_in_page = response_data.get('value', [])
                if not isinstance(items_in_page, list): break
                for item in items_in_page:
                    if len(all_items) < max_items_total: all_items.append(item)
                    else: break
                current_url = response_data.get('@odata.nextLink')
                if not current_url or len(all_items) >= max_items_total: break
            else: break
        
        logger.info(f"Total items OD recuperados: {len(all_items)} ({page_count} pág).")
        return {"status": "success", "data": all_items, "total_retrieved": len(all_items), "pages_processed": page_count}
    except Exception as e:
        logger.error(f"Error listando archivos OneDrive: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al listar archivos OneDrive: {type(e).__name__}", "http_status": status_code, "details": details}

def subir_archivo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    nombre_archivo: Optional[str] = parametros.get("nombre_archivo")
    contenido_bytes: Optional[bytes] = parametros.get("contenido_bytes")
    ruta_destino_relativa: str = parametros.get("ruta", "/")
    conflict_behavior: str = parametros.get("conflict_behavior", "rename")
    if not nombre_archivo or contenido_bytes is None or not isinstance(contenido_bytes, bytes):
        return {"status": "error", "message": "Parámetros 'nombre_archivo' y 'contenido_bytes' (bytes) son requeridos."}

    clean_folder_path = ruta_destino_relativa.strip('/')
    target_file_path_in_drive = f"/{nombre_archivo}" if not clean_folder_path else f"/{clean_folder_path}/{nombre_archivo}"
    item_endpoint_for_session = _get_od_me_item_path_endpoint(target_file_path_in_drive)
    file_size_mb = len(contenido_bytes) / (1024.0 * 1024.0)
    logger.info(f"Subiendo a OneDrive /me: '{target_file_path_in_drive}' ({file_size_mb:.2f} MB), conflict: '{conflict_behavior}'")

    try:
        if file_size_mb > 4.0:
            logger.info("Archivo > 4MB. Iniciando sesión de carga para OneDrive.")
            create_session_url = f"{item_endpoint_for_session}:/createUploadSession"
            session_body = {"item": {"@microsoft.graph.conflictBehavior": conflict_behavior, "name": nombre_archivo }}
            session_info = hacer_llamada_api("POST", create_session_url, headers, json_data=session_body, timeout=GRAPH_API_DEFAULT_TIMEOUT)
            upload_url = session_info.get("uploadUrl") if isinstance(session_info, dict) else None
            if not upload_url: raise ValueError("No se pudo obtener 'uploadUrl' de la sesión de carga OneDrive.")
            logger.info(f"Sesión de carga OD creada. URL (preview): {upload_url[:50]}...")

            chunk_size = 5 * 1024 * 1024; start_byte = 0; total_bytes = len(contenido_bytes)
            final_item_metadata = {}
            while start_byte < total_bytes:
                end_byte = min(start_byte + chunk_size - 1, total_bytes - 1)
                current_chunk_data = contenido_bytes[start_byte : end_byte + 1]
                content_range_header = f"bytes {start_byte}-{end_byte}/{total_bytes}"
                chunk_headers = {'Content-Length': str(len(current_chunk_data)), 'Content-Range': content_range_header}
                logger.debug(f"Subiendo chunk OD: {content_range_header}")
                chunk_upload_timeout = max(GRAPH_API_DEFAULT_TIMEOUT, int(file_size_mb * 6))
                chunk_response = requests.put(upload_url, headers=chunk_headers, data=current_chunk_data, timeout=chunk_upload_timeout)
                chunk_response.raise_for_status()
                start_byte = end_byte + 1
                if chunk_response.content:
                    try: final_item_metadata = chunk_response.json()
                    except json.JSONDecodeError: pass
                    if chunk_response.status_code in [200, 201] and final_item_metadata.get("id"): break
            
            logger.info(f"Archivo '{nombre_archivo}' subido a OD (sesión).")
            return {"status": "success", "data": final_item_metadata, "message": "Archivo subido con sesión de carga."}
        else:
            logger.info("Archivo <= 4MB. Usando subida simple para OneDrive.")
            url_put_simple = f"{item_endpoint_for_session}:/content"
            params_q = {"@microsoft.graph.conflictBehavior": conflict_behavior}
            upload_headers = headers.copy(); upload_headers['Content-Type'] = 'application/octet-stream'
            simple_timeout = max(GRAPH_API_DEFAULT_TIMEOUT, int(file_size_mb * 15) if file_size_mb > 0 else GRAPH_API_DEFAULT_TIMEOUT)
            resultado = hacer_llamada_api("PUT", url_put_simple, upload_headers, params=params_q, data=contenido_bytes, timeout=simple_timeout)
            logger.info(f"Archivo '{nombre_archivo}' subido a OD (simple). ID: {resultado.get('id') if isinstance(resultado, dict) else 'N/A'}")
            return {"status": "success", "data": resultado, "message": "Archivo subido con método simple."}
    except Exception as e:
        logger.error(f"Error subiendo a OneDrive '{nombre_archivo}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al subir archivo a OneDrive: {type(e).__name__}", "http_status": status_code, "details": details}

def descargar_archivo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Union[bytes, Dict[str, Any]]:
    item_path_or_id: Optional[str] = parametros.get("item_id_o_nombre_con_ruta")
    if not item_path_or_id:
        return {"status": "error", "message": "Parámetro 'item_id_o_nombre_con_ruta' es requerido."}

    if "/" in item_path_or_id or "." in item_path_or_id.split('/')[-1]:
        item_endpoint = _get_od_me_item_path_endpoint(item_path_or_id)
    else:
        item_endpoint = f"{_get_od_me_drive_endpoint()}/items/{item_path_or_id}"
        
    url = f"{item_endpoint}/content"
    logger.info(f"Descargando archivo OneDrive /me: '{item_path_or_id}'")
    download_timeout = max(GRAPH_API_DEFAULT_TIMEOUT, 120)
    try:
        file_bytes = hacer_llamada_api("GET", url, headers, timeout=download_timeout, expect_json=False, stream=True)
        if isinstance(file_bytes, bytes):
            logger.info(f"Archivo OneDrive '{item_path_or_id}' descargado ({len(file_bytes)} bytes).")
            # Devolver bytes directamente. El llamador decidirá qué hacer (guardar, convertir a base64, etc.)
            return file_bytes
        else:
             logger.error(f"Helper devolvió tipo inesperado {type(file_bytes)} al descargar archivo OD.")
             return {"status": "error", "message": "Error interno al descargar archivo (respuesta inesperada del helper)."}
    except Exception as e:
        logger.error(f"Error descargando archivo OneDrive '{item_path_or_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            if status_code == 404: return {"status": "error", "message": f"Archivo '{item_path_or_id}' no encontrado en OneDrive.", "details": details}
        return {"status": "error", "message": f"Error al descargar archivo OD: {type(e).__name__}", "http_status": status_code, "details": details}

def eliminar_archivo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    item_path_or_id: Optional[str] = parametros.get("item_id_o_nombre_con_ruta")
    if not item_path_or_id:
        return {"status": "error", "message": "Parámetro 'item_id_o_nombre_con_ruta' es requerido."}

    if "/" in item_path_or_id or "." in item_path_or_id.split('/')[-1]:
        item_endpoint = _get_od_me_item_path_endpoint(item_path_or_id)
    else:
        item_endpoint = f"{_get_od_me_drive_endpoint()}/items/{item_path_or_id}"
        
    url = item_endpoint
    logger.info(f"Eliminando archivo/carpeta OneDrive /me: '{item_path_or_id}'")
    try:
        hacer_llamada_api("DELETE", url, headers, timeout=GRAPH_API_DEFAULT_TIMEOUT, expect_json=False) # 204 No Content
        return {"status": "success", "message": f"Elemento '{item_path_or_id}' eliminado de OneDrive."}
    except Exception as e:
        logger.error(f"Error eliminando item OneDrive '{item_path_or_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            if status_code == 404: return {"status": "error", "message": f"Elemento '{item_path_or_id}' no encontrado para eliminar.", "details": details}
        return {"status": "error", "message": f"Error al eliminar item de OneDrive: {type(e).__name__}", "http_status": status_code, "details": details}

def crear_carpeta(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    nombre_carpeta: Optional[str] = parametros.get("nombre_carpeta")
    ruta_padre_relativa: str = parametros.get("ruta_padre", "/")
    conflict_behavior: str = parametros.get("conflict_behavior", "rename")
    if not nombre_carpeta:
        return {"status": "error", "message": "Parámetro 'nombre_carpeta' es requerido."}

    parent_folder_item_endpoint = _get_od_me_item_path_endpoint(ruta_padre_relativa)
    url = f"{parent_folder_item_endpoint}/children"
    body: Dict[str, Any] = {"name": nombre_carpeta, "folder": {}, "@microsoft.graph.conflictBehavior": conflict_behavior}
    
    logger.info(f"Creando carpeta OneDrive /me: '{nombre_carpeta}' en ruta padre '{ruta_padre_relativa}'")
    try:
        folder_data = hacer_llamada_api("POST", url, headers, json_data=body, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": folder_data, "message": f"Carpeta '{nombre_carpeta}' creada."}
    except Exception as e:
        logger.error(f"Error creando carpeta OneDrive '{nombre_carpeta}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al crear carpeta OneDrive: {type(e).__name__}", "http_status": status_code, "details": details}

# --- Funciones Añadidas/Completadas ---

def mover_archivo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    item_path_or_id_origen: Optional[str] = parametros.get("item_id_o_nombre_con_ruta_origen")
    nueva_ruta_carpeta_padre: Optional[str] = parametros.get("nueva_ruta_carpeta_padre")
    nuevo_nombre: Optional[str] = parametros.get("nuevo_nombre") # Opcional para renombrar al mover

    if not item_path_or_id_origen or nueva_ruta_carpeta_padre is None: 
        return {"status": "error", "message":"Params 'item_id_o_nombre_con_ruta_origen' y 'nueva_ruta_carpeta_padre' requeridos."}

    try:
        # Obtener ID del drive /me/drive (necesario para la referencia de path absoluto)
        me_drive_id = _get_me_drive_id(headers)

        # Obtener endpoint del item de origen
        if "/" in item_path_or_id_origen or "." in item_path_or_id_origen.split('/')[-1]:
            item_origen_endpoint = _get_od_me_item_path_endpoint(item_path_or_id_origen)
            # Para PATCH necesitamos el nombre actual si no se provee nuevo_nombre
            if nuevo_nombre is None:
                 try:
                      origen_metadata = hacer_llamada_api("GET", item_origen_endpoint + "?$select=name", headers)
                      nombre_actual = origen_metadata.get("name") if isinstance(origen_metadata, dict) else None
                 except: nombre_actual = item_path_or_id_origen.split('/')[-1] # Fallback
            else: nombre_actual = nuevo_nombre
        else: # Asumir ID
            item_origen_endpoint = f"{_get_od_me_drive_endpoint()}/items/{item_path_or_id_origen}"
            if nuevo_nombre is None:
                 try:
                      origen_metadata = hacer_llamada_api("GET", item_origen_endpoint + "?$select=name", headers)
                      nombre_actual = origen_metadata.get("name") if isinstance(origen_metadata, dict) else None
                      if not nombre_actual: raise ValueError("No se pudo obtener nombre actual por ID")
                 except Exception as getNameErr:
                     logger.error(f"No se pudo obtener nombre actual para item ID {item_path_or_id_origen}: {getNameErr}")
                     return {"status":"error", "message": "No se pudo determinar el nombre actual del item para mover/renombrar."}
            else: nombre_actual = nuevo_nombre

        # Construir referencia a la carpeta padre de destino
        parent_dest_path = nueva_ruta_carpeta_padre.strip()
        if not parent_dest_path.startswith('/'): parent_dest_path = '/' + parent_dest_path
        parent_reference_path = f"/drive/root" if parent_dest_path == '/' else f"/drive/root:{parent_dest_path}"

        body: Dict[str, Any] = {
            "parentReference": {
                "driveId": me_drive_id, # Asumimos mover dentro del mismo drive /me
                "path": parent_reference_path 
            },
            "name": nuevo_nombre or nombre_actual # Usar nuevo nombre o el actual
        }
        
        url = item_origen_endpoint # PATCH sobre el item de origen
        logger.info(f"Moviendo OneDrive /me '{item_path_or_id_origen}' a '{parent_dest_path}' (nombre final: {body['name']})")
        
        moved_item_data = hacer_llamada_api("PATCH", url, headers, json_data=body, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": moved_item_data, "message": "Elemento movido/renombrado."}

    except Exception as e:
        logger.error(f"Error moviendo item OneDrive '{item_path_or_id_origen}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al mover item OneDrive: {type(e).__name__}", "http_status": status_code, "details": details}

def copiar_archivo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    item_path_or_id_origen: Optional[str] = parametros.get("item_id_o_nombre_con_ruta_origen")
    nueva_ruta_carpeta_padre: Optional[str] = parametros.get("nueva_ruta_carpeta_padre")
    nuevo_nombre_copia: Optional[str] = parametros.get("nuevo_nombre_copia") # Opcional
    if not item_path_or_id_origen or nueva_ruta_carpeta_padre is None: 
        return {"status": "error", "message":"Params 'item_id_o_nombre_con_ruta_origen' y 'nueva_ruta_carpeta_padre' requeridos."}

    try:
        me_drive_id = _get_me_drive_id(headers) # Necesitamos el ID del drive

        # Endpoint del item de origen
        if "/" in item_path_or_id_origen or "." in item_path_or_id_origen.split('/')[-1]:
            item_origen_endpoint = _get_od_me_item_path_endpoint(item_path_or_id_origen)
            nombre_origen = item_path_or_id_origen.split('/')[-1] # Obtener nombre del path
        else: # Asumir ID
            item_origen_endpoint = f"{_get_od_me_drive_endpoint()}/items/{item_path_or_id_origen}"
            # Obtener nombre original para usarlo si no se da 'nuevo_nombre_copia'
            try:
                 origen_metadata = hacer_llamada_api("GET", item_origen_endpoint + "?$select=name", headers)
                 nombre_origen = origen_metadata.get("name") if isinstance(origen_metadata, dict) else None
                 if not nombre_origen: raise ValueError("No se pudo obtener nombre del item original por ID.")
            except Exception as getNameErr:
                return {"status":"error", "message": f"No se pudo obtener nombre del item original '{item_path_or_id_origen}' para copiar: {getNameErr}"}

        url = f"{item_origen_endpoint}/copy" # Endpoint para la acción de copia

        # Referencia a carpeta padre destino (dentro del mismo drive /me)
        parent_dest_path = nueva_ruta_carpeta_padre.strip()
        if not parent_dest_path.startswith('/'): parent_dest_path = '/' + parent_dest_path
        parent_reference_path = f"/drive/root" if parent_dest_path == '/' else f"/drive/root:{parent_dest_path}"

        body: Dict[str, Any] = {
            "parentReference": {"driveId": me_drive_id, "path": parent_reference_path},
            "name": nuevo_nombre_copia or f"Copia de {nombre_origen}" # Nombre para la copia
        }
        
        logger.info(f"Iniciando copia asíncrona OneDrive /me de '{item_path_or_id_origen}' a '{nueva_ruta_carpeta_padre}'")
        
        # POST a /copy devuelve 202 Accepted con cabecera Location
        response_obj = hacer_llamada_api("POST", url, headers, json_data=body, timeout=GRAPH_API_DEFAULT_TIMEOUT, expect_json=False)

        if isinstance(response_obj, requests.Response) and response_obj.status_code == 202:
            monitor_url = response_obj.headers.get('Location')
            logger.info(f"Copia OneDrive iniciada. Monitor URL: {monitor_url}")
            return {"status": "success", "message": "Copia iniciada.", "monitorUrl": monitor_url, "status_code": 202}
        else:
            # Algo salió mal si no obtuvimos un Response 202
            status_code = response_obj.status_code if isinstance(response_obj, requests.Response) else 500
            details = response_obj.text[:200] if isinstance(response_obj, requests.Response) else f"Tipo de respuesta inesperado: {type(response_obj)}"
            logger.error(f"Respuesta inesperada al iniciar copia OneDrive: {status_code}. Detalles: {details}")
            return {"status": "error", "message": f"Respuesta inesperada {status_code} al iniciar copia.", "details": details}

    except Exception as e:
        logger.error(f"Error copiando item OneDrive '{item_path_or_id_origen}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al copiar item OneDrive: {type(e).__name__}", "http_status": status_code, "details": details}


def actualizar_metadatos_archivo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    item_path_or_id: Optional[str] = parametros.get("item_id_o_nombre_con_ruta")
    nuevos_valores: Optional[Dict[str, Any]] = parametros.get("nuevos_valores")
    if not item_path_or_id or not nuevos_valores or not isinstance(nuevos_valores, dict):
        return {"status":"error", "message":"Params 'item_id_o_nombre_con_ruta' y 'nuevos_valores' (dict) requeridos."}

    if "/" in item_path_or_id or "." in item_path_or_id.split('/')[-1]:
        item_endpoint = _get_od_me_item_path_endpoint(item_path_or_id)
    else:
        item_endpoint = f"{_get_od_me_drive_endpoint()}/items/{item_path_or_id}"
    
    url = item_endpoint # PATCH sobre el item
    current_headers = headers.copy()
    body_data = nuevos_valores.copy()
    etag = body_data.pop('@odata.etag', None)
    if etag: current_headers['If-Match'] = etag; logger.debug("Usando ETag para actualizar metadatos OD.")
    
    logger.info(f"Actualizando metadatos OneDrive /me: '{item_path_or_id}'")
    try:
        updated_metadata = hacer_llamada_api("PATCH", url, current_headers, json_data=body_data, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": updated_metadata, "message": "Metadatos actualizados."}
    except Exception as e:
        logger.error(f"Error actualizando metadatos OneDrive '{item_path_or_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            if status_code == 412: return {"status": "error", "message": "Conflicto de concurrencia (ETag).", "details": details}
        return {"status": "error", "message": f"Error al actualizar metadatos: {type(e).__name__}", "http_status": status_code, "details": details}


# --- FIN DEL MÓDULO actions/onedrive_actions.py ---