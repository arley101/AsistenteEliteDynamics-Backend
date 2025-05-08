# MyHttpTrigger/actions/sharepoint_actions.py
import logging
import requests # Necesario aquí solo para tipos de excepción (RequestException)
import os
import json # Para formateo de exportación y memoria
import csv # Para exportación CSV
from io import StringIO # Para exportación CSV
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone # Asegurar importación de timezone

# Importar helper y constantes desde la estructura compartida
try:
    from ..shared.helpers.http_client import hacer_llamada_api
    from ..shared.constants import BASE_URL, GRAPH_API_DEFAULT_TIMEOUT, APP_NAME
except ImportError as e:
    logging.critical(f"Error CRÍTICO importando helpers/constantes en SharePoint: {e}. Verifica la estructura.", exc_info=True)
    BASE_URL = "https://graph.microsoft.com/v1.0"
    GRAPH_API_DEFAULT_TIMEOUT = 45
    APP_NAME="EliteDynamicsPro" # Fallback
    def hacer_llamada_api(*args, **kwargs): # type: ignore
        raise NotImplementedError("Dependencia 'hacer_llamada_api' no importada correctamente.")

logger = logging.getLogger(f"{APP_NAME}.actions.sharepoint")

# --- Configuración Leída de Variables de Entorno ---
SHAREPOINT_DEFAULT_SITE_ID = os.environ.get('SHAREPOINT_DEFAULT_SITE_ID')
SHAREPOINT_DEFAULT_DRIVE_ID = os.environ.get('SHAREPOINT_DEFAULT_DRIVE_ID', 'Documents')
MEMORIA_LIST_NAME = os.environ.get('SHAREPOINT_MEMORY_LIST', 'AsistenteMemoriaPersistente')

# --- Helper Interno para Obtener Site ID ---
def _obtener_site_id_sp(parametros: Dict[str, Any], headers: Dict[str, str]) -> str:
    site_id_input: Optional[str] = parametros.get("site_id")
    if site_id_input and ',' in site_id_input:
        logger.debug(f"Usando Site ID directo proporcionado: {site_id_input}")
        return site_id_input
    if site_id_input and (':' in site_id_input or '.' in site_id_input):
        site_path_lookup = site_id_input if ':' in site_id_input else f"{site_id_input}:/"
        url = f"{BASE_URL}/sites/{site_path_lookup}?$select=id"
        try:
            logger.debug(f"Buscando Site ID por path/hostname: GET {url}")
            site_data = hacer_llamada_api("GET", url, headers, timeout=GRAPH_API_DEFAULT_TIMEOUT)
            site_id = site_data.get("id") if isinstance(site_data, dict) else None
            if site_id:
                logger.info(f"Site ID encontrado por path/hostname '{site_id_input}': {site_id}")
                return site_id
            raise ValueError(f"Respuesta inválida de Graph API buscando sitio '{site_id_input}'.")
        except requests.exceptions.RequestException as e:
            if e.response is not None and e.response.status_code == 404:
                logger.warning(f"No se encontró sitio por path/hostname '{site_id_input}' (404).")
            else:
                logger.warning(f"Error API buscando sitio por path/hostname '{site_id_input}': {e}.")
        except Exception as e:
            logger.warning(f"Error inesperado buscando sitio por path/hostname '{site_id_input}': {e}.")

    if SHAREPOINT_DEFAULT_SITE_ID:
        logger.debug(f"Usando Site ID por defecto de variable de entorno: {SHAREPOINT_DEFAULT_SITE_ID}")
        return SHAREPOINT_DEFAULT_SITE_ID
    
    url = f"{BASE_URL}/sites/root?$select=id" # Obtener el sitio raíz del tenant como último recurso
    try:
        logger.debug(f"Obteniendo sitio raíz SP del tenant: GET {url}")
        site_data = hacer_llamada_api("GET", url, headers, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        site_id = site_data.get("id") if isinstance(site_data, dict) else None
        if not site_id: raise ValueError("Respuesta de sitio raíz inválida, falta 'id'.")
        logger.info(f"Site ID raíz del tenant obtenido: {site_id}")
        return site_id
    except Exception as e:
        logger.critical(f"Fallo crítico al obtener Site ID (ni input, ni default, ni raíz funcionaron): {e}", exc_info=True)
        raise ValueError(f"No se pudo determinar el Site ID de SharePoint: {e}") from e

def _get_sp_drive_endpoint(site_id: str, drive_id_or_name: Optional[str] = None) -> str:
    target_drive = drive_id_or_name or SHAREPOINT_DEFAULT_DRIVE_ID or 'Documents'
    return f"{BASE_URL}/sites/{site_id}/drives/{target_drive}"

def _get_sp_item_path_endpoint(site_id: str, item_path: str, drive_id_or_name: Optional[str] = None) -> str:
    drive_endpoint = _get_sp_drive_endpoint(site_id, drive_id_or_name)
    safe_path = item_path.strip()
    if not safe_path or safe_path == '/': return f"{drive_endpoint}/root"
    if not safe_path.startswith('/'): safe_path = '/' + safe_path
    return f"{drive_endpoint}/root:{safe_path}"

def _get_drive_id(headers: Dict[str, str], site_id: str, drive_id_or_name: Optional[str] = None) -> str:
    drive_name_for_log = drive_id_or_name or SHAREPOINT_DEFAULT_DRIVE_ID or 'Documents'
    drive_endpoint = _get_sp_drive_endpoint(site_id, drive_id_or_name)
    url = f"{drive_endpoint}?$select=id"
    try:
        logger.debug(f"Obteniendo Drive ID para '{drive_name_for_log}': GET {url}")
        drive_data = hacer_llamada_api("GET", url, headers, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        actual_drive_id = drive_data.get('id') if isinstance(drive_data, dict) else None
        if not actual_drive_id: raise ValueError("Respuesta inválida, no se pudo obtener 'id' del drive.")
        logger.info(f"Drive ID obtenido para '{drive_name_for_log}': {actual_drive_id}")
        return actual_drive_id
    except Exception as e:
        logger.error(f"Error API obteniendo Drive ID para '{drive_name_for_log}': {e}", exc_info=True)
        raise Exception(f"Error obteniendo Drive ID para biblioteca '{drive_name_for_log}': {e}") from e

# ============================================
# ==== ACCIONES PARA LISTAS SHAREPOINT ====
# ============================================
def crear_lista(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    nombre_lista: Optional[str] = parametros.get("nombre_lista")
    columnas: Optional[List[Dict[str, Any]]] = parametros.get("columnas")
    if not nombre_lista: raise ValueError("Parámetro 'nombre_lista' es requerido.")
    if columnas and not isinstance(columnas, list): raise ValueError("Parámetro 'columnas' debe ser una lista de diccionarios.")

    target_site_id = _obtener_site_id_sp(parametros, headers)
    url = f"{BASE_URL}/sites/{target_site_id}/lists"
    body = {"displayName": nombre_lista, "columns": columnas or [], "list": {"template": "genericList"}}
    logger.info(f"Creando lista SP '{nombre_lista}' en sitio {target_site_id}")
    return hacer_llamada_api("POST", url, headers, json_data=body, timeout=GRAPH_API_DEFAULT_TIMEOUT)

def listar_listas(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    select: str = parametros.get("select", "id,name,displayName,webUrl")
    target_site_id = _obtener_site_id_sp(parametros, headers)
    url = f"{BASE_URL}/sites/{target_site_id}/lists"
    params_query = {"$select": select} if select else None
    logger.info(f"Listando listas SP del sitio {target_site_id} (campos: {select})")
    return hacer_llamada_api("GET", url, headers, params=params_query, timeout=GRAPH_API_DEFAULT_TIMEOUT)

def agregar_elemento_lista(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    lista_id_o_nombre: Optional[str] = parametros.get("lista_id_o_nombre")
    datos_campos: Optional[Dict[str, Any]] = parametros.get("datos_campos")
    if not lista_id_o_nombre: raise ValueError("Parámetro 'lista_id_o_nombre' es requerido.")
    if not datos_campos or not isinstance(datos_campos, dict): raise ValueError("Parámetro 'datos_campos' (diccionario) es requerido.")
    target_site_id = _obtener_site_id_sp(parametros, headers)
    body = {"fields": datos_campos}
    url = f"{BASE_URL}/sites/{target_site_id}/lists/{lista_id_o_nombre}/items"
    logger.info(f"Agregando elemento a lista SP '{lista_id_o_nombre}' en sitio {target_site_id}")
    return hacer_llamada_api("POST", url, headers, json_data=body, timeout=GRAPH_API_DEFAULT_TIMEOUT)

def listar_elementos_lista(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    lista_id_o_nombre: Optional[str] = parametros.get("lista_id_o_nombre")
    expand_fields: bool = parametros.get("expand_fields", True)
    top: int = int(parametros.get("top", 100))
    filter_query: Optional[str] = parametros.get("filter_query")
    select: Optional[str] = parametros.get("select") # Puede ser string "field1,field2" o "fields/field1,fields/field2"
    order_by: Optional[str] = parametros.get("order_by")
    if not lista_id_o_nombre: raise ValueError("Parámetro 'lista_id_o_nombre' es requerido.")

    target_site_id = _obtener_site_id_sp(parametros, headers)
    url_base = f"{BASE_URL}/sites/{target_site_id}/lists/{lista_id_o_nombre}/items"
    
    params_q: Dict[str, Any] = {'$top': min(top, 999)}
    if expand_fields and not (select and "fields" in select.lower()): # Si no se expande vía select
        params_q['$expand'] = 'fields'
    if select: params_q['$select'] = select
    if filter_query: params_q['$filter'] = filter_query
    if order_by: params_q['$orderby'] = order_by
    
    all_items: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0; max_pages = 100
    try:
        while current_url and page_count < max_pages:
            page_count += 1; logger.info(f"Listando elementos SP lista '{lista_id_o_nombre}', Página: {page_count}")
            current_params_for_call = params_q if page_count == 1 else None
            data = hacer_llamada_api("GET", current_url, headers, params=current_params_for_call, timeout=GRAPH_API_DEFAULT_TIMEOUT)
            if data and isinstance(data, dict):
                page_items = data.get('value', []); all_items.extend(page_items)
                current_url = data.get('@odata.nextLink')
                if not current_url: break
            else: logger.warning(f"Paginación de lista SP: respuesta inesperada o vacía. Terminando."); break
        if page_count >= max_pages: logger.warning(f"Límite de {max_pages} páginas alcanzado.")
        logger.info(f"Total elementos SP lista '{lista_id_o_nombre}': {len(all_items)}")
        return {'value': all_items, '@odata.count': len(all_items)} # Añadir count
    except Exception as e:
        logger.error(f"Error listando elementos SP: {e}", exc_info=True); raise

def actualizar_elemento_lista(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    lista_id_o_nombre: Optional[str] = parametros.get("lista_id_o_nombre")
    item_id: Optional[str] = parametros.get("item_id")
    nuevos_valores_campos: Optional[Dict[str, Any]] = parametros.get("nuevos_valores_campos")
    if not all([lista_id_o_nombre, item_id, nuevos_valores_campos]): raise ValueError("Faltan parámetros requeridos.")
    if not isinstance(nuevos_valores_campos, dict): raise ValueError("'nuevos_valores_campos' debe ser un diccionario.")

    target_site_id = _obtener_site_id_sp(parametros, headers)
    url = f"{BASE_URL}/sites/{target_site_id}/lists/{lista_id_o_nombre}/items/{item_id}/fields"
    current_headers = headers.copy(); body_data = nuevos_valores_campos.copy()
    etag = body_data.pop('@odata.etag', None)
    if etag: current_headers['If-Match'] = etag; logger.debug(f"Usando ETag '{etag}'.")
    logger.info(f"Actualizando elemento SP '{item_id}' en lista '{lista_id_o_nombre}'")
    return hacer_llamada_api("PATCH", url, current_headers, json_data=body_data, timeout=GRAPH_API_DEFAULT_TIMEOUT)

def eliminar_elemento_lista(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    lista_id_o_nombre: Optional[str] = parametros.get("lista_id_o_nombre")
    item_id: Optional[str] = parametros.get("item_id")
    etag: Optional[str] = parametros.get("etag")
    if not all([lista_id_o_nombre, item_id]): raise ValueError("Faltan parámetros requeridos.")

    target_site_id = _obtener_site_id_sp(parametros, headers)
    url = f"{BASE_URL}/sites/{target_site_id}/lists/{lista_id_o_nombre}/items/{item_id}"
    current_headers = headers.copy()
    if etag: current_headers['If-Match'] = etag; logger.debug(f"Usando ETag '{etag}'.")
    else: logger.warning(f"Eliminando item SP {item_id} sin ETag.")
    logger.info(f"Eliminando elemento SP '{item_id}' de lista '{lista_id_o_nombre}'")
    hacer_llamada_api("DELETE", url, current_headers, timeout=GRAPH_API_DEFAULT_TIMEOUT)
    return {"status": "success", "message": "Elemento eliminado", "item_id": item_id, "lista": lista_id_o_nombre}

# ========================================================
# ==== ACCIONES PARA DOCUMENTOS (BIBLIOTECAS/DRIVES) ====
# ========================================================
# Renombrando funciones para claridad y evitar colisiones con OneDrive si se importan directamente
def listar_documentos_biblioteca(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    biblioteca: Optional[str] = parametros.get("biblioteca")
    ruta_carpeta: str = parametros.get("ruta_carpeta", '/')
    top: int = int(parametros.get("top", 100))
    target_site_id = _obtener_site_id_sp(parametros, headers)
    item_endpoint = _get_sp_item_path_endpoint(target_site_id, ruta_carpeta, biblioteca)
    url_base = f"{item_endpoint}/children"
    params_q = {'$top': min(top, 999)}
    all_files: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base; page_count = 0; max_pages = 100
    try:
        while current_url and page_count < max_pages:
            page_count += 1; drive_name = biblioteca or SHAREPOINT_DEFAULT_DRIVE_ID or 'Documents'
            logger.info(f"Listando docs SP biblio '{drive_name}', Ruta: '{ruta_carpeta}', Pág: {page_count}")
            current_params_for_call = params_q if page_count == 1 else None
            data = hacer_llamada_api("GET", current_url, headers, params=current_params_for_call, timeout=GRAPH_API_DEFAULT_TIMEOUT)
            if data and isinstance(data, dict):
                page_items = data.get('value', []); all_files.extend(page_items)
                current_url = data.get('@odata.nextLink')
                if not current_url: break
            else: logger.warning(f"Paginación SP docs: respuesta inesperada/vacía."); break
        if page_count >= max_pages: logger.warning(f"Límite {max_pages} págs listando docs en '{ruta_carpeta}'.")
        logger.info(f"Total docs/carpetas SP encontrados: {len(all_files)}")
        return {'value': all_files, '@odata.count': len(all_files)}
    except Exception as e:
        logger.error(f"Error listando docs SP: {e}", exc_info=True); raise

def subir_documento(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    nombre_archivo: Optional[str] = parametros.get("nombre_archivo")
    contenido_bytes: Optional[bytes] = parametros.get("contenido_bytes")
    biblioteca: Optional[str] = parametros.get("biblioteca")
    ruta_carpeta_destino: str = parametros.get("ruta_carpeta_destino", '/')
    conflict_behavior: str = parametros.get("conflict_behavior", "rename")
    if not nombre_archivo or contenido_bytes is None or not isinstance(contenido_bytes, bytes):
        raise ValueError("Parámetros 'nombre_archivo' y 'contenido_bytes' (bytes) son requeridos.")

    target_site_id = _obtener_site_id_sp(parametros, headers)
    target_drive = biblioteca or SHAREPOINT_DEFAULT_DRIVE_ID or 'Documents'
    folder_path = ruta_carpeta_destino.strip('/')
    file_path_in_drive = f"/{nombre_archivo}" if not folder_path else f"/{folder_path}/{nombre_archivo}"
    item_endpoint = _get_sp_item_path_endpoint(target_site_id, file_path_in_drive, target_drive)
    
    file_size_mb = len(contenido_bytes) / (1024 * 1024)
    logger.info(f"Subiendo doc SP '{nombre_archivo}' ({file_size_mb:.2f} MB) a '{ruta_carpeta_destino}' en biblio '{target_drive}'")

    if file_size_mb > 4.0: # Sesión de carga para archivos grandes
        create_session_url = f"{item_endpoint}:/createUploadSession"
        session_body = {"item": {"@microsoft.graph.conflictBehavior": conflict_behavior, "name": nombre_archivo}} # Pasar nombre aquí
        try:
            logger.info("Archivo > 4MB. Creando sesión de carga SP...")
            session_info = hacer_llamada_api("POST", create_session_url, headers, json_data=session_body, timeout=GRAPH_API_DEFAULT_TIMEOUT)
            upload_url = session_info.get("uploadUrl") if isinstance(session_info, dict) else None
            if not upload_url: raise ValueError("No se pudo obtener 'uploadUrl' de la sesión de carga SP.")
            
            # Subir fragmentos (simplificado, para producción se necesitan más reintentos y manejo robusto de chunks)
            chunk_size = 5 * 1024 * 1024; start_byte = 0; total_bytes = len(contenido_bytes)
            final_response_json = {}
            while start_byte < total_bytes:
                end_byte = min(start_byte + chunk_size - 1, total_bytes - 1)
                chunk_data = contenido_bytes[start_byte : end_byte + 1]
                content_range = f"bytes {start_byte}-{end_byte}/{total_bytes}"
                chunk_headers = {'Content-Length': str(len(chunk_data)), 'Content-Range': content_range}
                logger.debug(f"Subiendo chunk SP: {content_range}")
                # Usar requests directo para la URL de sesión (no necesita auth header MSAL)
                chunk_timeout = max(GRAPH_API_DEFAULT_TIMEOUT, int(file_size_mb * 5))
                chunk_resp = requests.put(upload_url, headers=chunk_headers, data=chunk_data, timeout=chunk_timeout)
                chunk_resp.raise_for_status()
                start_byte = end_byte + 1
                if chunk_resp.content: # La última respuesta (201 o 200) tiene los metadatos
                    try: final_response_json = chunk_resp.json()
                    except json.JSONDecodeError: pass
            logger.info(f"Doc SP '{nombre_archivo}' subido exitosamente mediante sesión de carga.")
            return final_response_json if final_response_json else {"status": "success", "message": "Subida grande completada, pero sin metadatos de respuesta."}
        except Exception as e:
            logger.error(f"Error en sesión de carga SP para '{nombre_archivo}': {e}", exc_info=True); raise
    else: # Subida simple
        url_put = f"{item_endpoint}:/content"
        params_q = {"@microsoft.graph.conflictBehavior": conflict_behavior}
        upload_headers = headers.copy(); upload_headers['Content-Type'] = 'application/octet-stream'
        simple_timeout = max(GRAPH_API_DEFAULT_TIMEOUT, int(file_size_mb * 10) if file_size_mb > 0 else GRAPH_API_DEFAULT_TIMEOUT)
        resultado = hacer_llamada_api("PUT", url_put, upload_headers, params=params_q, data=contenido_bytes, timeout=simple_timeout, expect_json=True)
        logger.info(f"Doc SP '{nombre_archivo}' subido (subida simple). ID: {resultado.get('id') if isinstance(resultado, dict) else 'N/A'}")
        return resultado if isinstance(resultado, dict) else {"status":"error", "message":"Respuesta inesperada en subida simple"}

# Renombrar las siguientes funciones para que coincidan con lo esperado por mapping_actions.py
def eliminar_archivo_biblioteca(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    # Esta es la lógica de la función 'eliminar_archivo' de tu ejemplo original
    nombre_item: Optional[str] = parametros.get("nombre_archivo_o_carpeta") # Cambiar nombre de param si es necesario
    biblioteca: Optional[str] = parametros.get("biblioteca")
    ruta_carpeta: str = parametros.get("ruta_carpeta", '/')
    if not nombre_item: raise ValueError("Parámetro 'nombre_archivo_o_carpeta' es requerido.")
    target_site_id = _obtener_site_id_sp(parametros, headers)
    folder_path = ruta_carpeta.strip('/')
    item_path = f"/{nombre_item}" if not folder_path else f"/{folder_path}/{nombre_item}"
    item_endpoint = _get_sp_item_path_endpoint(target_site_id, item_path, biblioteca)
    logger.info(f"Eliminando '{item_path}' en biblio '{biblioteca or 'default'}' del sitio '{target_site_id}'")
    hacer_llamada_api("DELETE", item_endpoint, headers, timeout=GRAPH_API_DEFAULT_TIMEOUT)
    return {"status": "success", "message": f"Elemento '{item_path}' eliminado."}

def crear_carpeta_biblioteca(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    # Lógica de tu función original crear_carpeta_biblioteca
    nombre_carpeta: Optional[str] = parametros.get("nombre_carpeta")
    biblioteca: Optional[str] = parametros.get("biblioteca")
    ruta_padre: str = parametros.get("ruta_carpeta_padre", '/')
    conflict: str = parametros.get("conflict_behavior", "rename")
    if not nombre_carpeta: raise ValueError("Parámetro 'nombre_carpeta' es requerido.")
    target_site_id = _obtener_site_id_sp(parametros, headers)
    parent_endpoint = _get_sp_item_path_endpoint(target_site_id, ruta_padre, biblioteca)
    url = f"{parent_endpoint}/children"
    body = {"name": nombre_carpeta, "folder": {}, "@microsoft.graph.conflictBehavior": conflict}
    logger.info(f"Creando carpeta SP '{nombre_carpeta}' en '{ruta_padre}'")
    return hacer_llamada_api("POST", url, headers, json_data=body, timeout=GRAPH_API_DEFAULT_TIMEOUT)

# Y así sucesivamente para mover_archivo_biblioteca, copiar_archivo_biblioteca, etc.
# Necesitas tomar la lógica de tus funciones 'mover_archivo', 'copiar_archivo', etc.
# y ponerlas aquí con los nuevos nombres de función que mapeaste.

# Ejemplo para una más (necesitarías completar el resto):
def mover_archivo_biblioteca(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    # Lógica de tu función original 'mover_archivo'
    nombre_item: Optional[str] = parametros.get("nombre_archivo_o_carpeta")
    ruta_origen: str = parametros.get("ruta_carpeta_origen", '/')
    nueva_ruta_padre: Optional[str] = parametros.get("nueva_ruta_carpeta_padre")
    nuevo_nombre: Optional[str] = parametros.get("nuevo_nombre")
    biblioteca: Optional[str] = parametros.get("biblioteca")
    if not nombre_item or nueva_ruta_padre is None: raise ValueError("Faltan params requeridos ('nombre_archivo_o_carpeta', 'nueva_ruta_carpeta_padre').")
    
    target_site_id = _obtener_site_id_sp(parametros, headers)
    drive_name_or_id = biblioteca or SHAREPOINT_DEFAULT_DRIVE_ID or "Documents"
    actual_drive_id = _get_drive_id(headers, target_site_id, drive_name_or_id)

    folder_path_origen = ruta_origen.strip('/')
    item_path_origen = f"/{nombre_item}" if not folder_path_origen else f"/{folder_path_origen}/{nombre_item}"
    item_origen_endpoint = _get_sp_item_path_endpoint(target_site_id, item_path_origen, drive_name_or_id)
    
    parent_dest_path = nueva_ruta_padre.strip()
    if not parent_dest_path.startswith('/'): parent_dest_path = '/' + parent_dest_path
    parent_ref_path = f"/drives/{actual_drive_id}/root" if parent_dest_path == '/' else f"/drives/{actual_drive_id}/root:{parent_dest_path}"
    
    body = {"parentReference": {"path": parent_ref_path}, "name": nuevo_nombre or nombre_item}
    logger.info(f"Moviendo SP '{item_path_origen}' a '{parent_dest_path}' (nuevo nombre: {body['name']})")
    return hacer_llamada_api("PATCH", item_origen_endpoint, headers, json_data=body, timeout=GRAPH_API_DEFAULT_TIMEOUT)

# --- DEBES CONTINUAR AQUÍ ---
# Replicar la lógica para:
# copiar_archivo_biblioteca (basado en tu copiar_archivo)
# obtener_metadatos_archivo_biblioteca (basado en tu obtener_metadatos_archivo)
# actualizar_metadatos_archivo_biblioteca (basado en tu actualizar_metadatos_archivo)
# obtener_contenido_archivo_biblioteca (basado en tu obtener_contenido_archivo)
# actualizar_contenido_archivo_biblioteca (basado en tu actualizar_contenido_archivo)
# crear_enlace_compartido_archivo_biblioteca (basado en tu crear_enlace_compartido_archivo)

# Las funciones de memoria y exportación ya tienen nombres únicos y deberían funcionar:
# guardar_dato_memoria, recuperar_datos_sesion, eliminar_dato_memoria, eliminar_memoria_sesion, exportar_datos_lista

# Solo asegúrate que las importaciones al inicio del archivo sean correctas:
# from ..shared.helpers.http_client import hacer_llamada_api
# from ..shared.constants import BASE_URL, GRAPH_API_DEFAULT_TIMEOUT
# La tuya tiene un try-except anidado que podría ser simplificado.

# El resto de tus funciones de memoria y exportación... (ya están bien nombradas en tu ejemplo)
def guardar_dato_memoria(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    session_id: Optional[str] = parametros.get("session_id")
    clave: Optional[str] = parametros.get("clave")
    valor: Any = parametros.get("valor")
    if not session_id or not clave or valor is None: raise ValueError("Params 'session_id', 'clave', 'valor' requeridos.")
    target_site_id = _obtener_site_id_sp(parametros, headers)
    if not _ensure_memory_list_exists(headers, target_site_id):
        raise Exception(f"No se pudo asegurar lista de memoria '{MEMORIA_LIST_NAME}'.")
    valor_str = json.dumps(valor) if isinstance(valor, (dict, list, bool)) else str(valor)
    
    filter_q = f"fields/SessionID eq '{session_id}' and fields/Clave eq '{clave}'"
    params_list = {"lista_id_o_nombre": MEMORIA_LIST_NAME, "site_id": target_site_id, "filter_query": filter_q, "top": 1, "select": "id,@odata.etag"}
    item_id, item_etag = None, None
    try:
        exist_data = listar_elementos_lista(params_list, headers) # type: ignore
        if exist_data.get("value"): item_id, item_etag = exist_data["value"][0].get("id"), exist_data["value"][0].get("@odata.etag")
    except Exception: logger.warning(f"Error buscando item de memoria, se intentará crear.")
        
    datos_campos = {"SessionID": session_id, "Clave": clave, "Valor": valor_str, "Timestamp": datetime.now(timezone.utc).isoformat()}
    if item_id:
        params_upd = {"lista_id_o_nombre": MEMORIA_LIST_NAME, "item_id": item_id, "nuevos_valores_campos": datos_campos, "site_id": target_site_id}
        if item_etag: params_upd["nuevos_valores_campos"]["@odata.etag"] = item_etag
        return actualizar_elemento_lista(params_upd, headers)
    else:
        params_add = {"lista_id_o_nombre": MEMORIA_LIST_NAME, "datos_campos": datos_campos, "site_id": target_site_id}
        return agregar_elemento_lista(params_add, headers)

def recuperar_datos_sesion(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    session_id: Optional[str] = parametros.get("session_id")
    if not session_id: raise ValueError("Parámetro 'session_id' es requerido.")
    target_site_id = _obtener_site_id_sp(parametros, headers)
    if not _ensure_memory_list_exists(headers, target_site_id): return {}
    
    filter_q = f"fields/SessionID eq '{session_id}'"
    params_list = {"lista_id_o_nombre": MEMORIA_LIST_NAME, "site_id": target_site_id, "filter_query": filter_q, "expand_fields": True, "select": "id,fields/Clave,fields/Valor,fields/Timestamp", "order_by": "fields/Timestamp desc", "top": 999}
    items_data = listar_elementos_lista(params_list, headers) # type: ignore
    memoria: Dict[str, Any] = {}
    for item in items_data.get("value", []):
        fields = item.get("fields", {}); clave = fields.get("Clave"); valor_str = fields.get("Valor")
        if clave and valor_str and clave not in memoria:
            try: memoria[clave] = json.loads(valor_str)
            except: memoria[clave] = valor_str
    logger.info(f"Recuperados {len(memoria)} datos para Session={session_id}")
    return memoria

def eliminar_dato_memoria(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    session_id: Optional[str] = parametros.get("session_id"); clave: Optional[str] = parametros.get("clave")
    if not session_id or not clave: raise ValueError("Params 'session_id' y 'clave' requeridos.")
    target_site_id = _obtener_site_id_sp(parametros, headers)
    if not _ensure_memory_list_exists(headers, target_site_id): return {"status": "Lista no encontrada"}

    filter_q = f"fields/SessionID eq '{session_id}' and fields/Clave eq '{clave}'"
    params_list = {"lista_id_o_nombre": MEMORIA_LIST_NAME, "site_id": target_site_id, "filter_query": filter_q, "top": 1, "select": "id"}
    item_id = None
    try:
        exist_data = listar_elementos_lista(params_list, headers) # type: ignore
        if exist_data.get("value"): item_id = exist_data["value"][0].get("id")
    except Exception as e: raise Exception(f"Error buscando item a eliminar: {e}") from e
    
    if item_id:
        params_del = {"lista_id_o_nombre": MEMORIA_LIST_NAME, "item_id": item_id, "site_id": target_site_id}
        return eliminar_elemento_lista(params_del, headers)
    else:
        return {"status": "No encontrado", "session_id": session_id, "clave": clave}

def eliminar_memoria_sesion(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    session_id: Optional[str] = parametros.get("session_id")
    if not session_id: raise ValueError("Parámetro 'session_id' es requerido.")
    target_site_id = _obtener_site_id_sp(parametros, headers)
    if not _ensure_memory_list_exists(headers, target_site_id): return {"status": "Lista no encontrada", "items_eliminados": 0}

    filter_q = f"fields/SessionID eq '{session_id}'"
    params_list = {"lista_id_o_nombre": MEMORIA_LIST_NAME, "site_id": target_site_id, "filter_query": filter_q, "select": "id", "top": 999}
    items_data = listar_elementos_lista(params_list, headers) # type: ignore
    item_ids_to_delete = [item.get("id") for item in items_data.get("value", []) if item.get("id")]
    
    if not item_ids_to_delete: return {"status": "Sin datos", "items_eliminados": 0, "session_id": session_id}
    
    count_deleted, count_failed = 0, 0
    for item_id_del in item_ids_to_delete:
        try:
            eliminar_elemento_lista({"lista_id_o_nombre": MEMORIA_LIST_NAME, "item_id": item_id_del, "site_id": target_site_id}, headers)
            count_deleted += 1
        except: count_failed += 1
    
    status_msg = "Completado" if count_failed == 0 else "Completado con errores"
    return {"status": status_msg, "items_eliminados": count_deleted, "items_fallidos": count_failed, "session_id": session_id}

def exportar_datos_lista(parametros: Dict[str, Any], headers: Dict[str, str]) -> Union[Dict[str, Any], str]:
    lista_id_o_nombre: Optional[str] = parametros.get("lista_id_o_nombre")
    formato: str = parametros.get("formato", "json").lower()
    if not lista_id_o_nombre or formato not in ["json", "csv"]: raise ValueError("Params 'lista_id_o_nombre' y 'formato' (json/csv) requeridos y válidos.")
    
    target_site_id = _obtener_site_id_sp(parametros, headers)
    params_list = {"lista_id_o_nombre": lista_id_o_nombre, "site_id": target_site_id, "expand_fields": True, "top": 999}
    items_data = listar_elementos_lista(params_list, headers) # type: ignore
    items = [dict(item.get("fields",{}), **{"_ItemID_": item.get("id")}) for item in items_data.get("value", [])]
    
    if not items: return {"value": []} if formato == "json" else ""
    if formato == "json": return {"value": items}
    else: # csv
        output = StringIO(); field_names = list(items[0].keys())
        if "_ItemID_" in field_names: field_names.insert(0, field_names.pop(field_names.index("_ItemID_")))
        writer = csv.DictWriter(output, fieldnames=field_names, extrasaction='ignore', quoting=csv.QUOTE_MINIMAL)
        writer.writeheader(); writer.writerows(items)
        return output.getvalue()

# --- FIN DEL MÓDULO ---