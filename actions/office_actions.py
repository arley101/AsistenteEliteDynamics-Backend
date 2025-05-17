# MyHttpTrigger/actions/office_actions.py
import logging
import requests # Solo para tipos de excepción
import json
import os
from typing import Dict, List, Optional, Union, Any

# Importar helper y constantes
try:
    from shared.helpers.http_client import hacer_llamada_api # Asumo que esta función existe y está definida en tu helper
    # Ajusta las siguientes importaciones según la ubicación real de tus constantes
    from shared.constants import BASE_URL, GRAPH_API_DEFAULT_TIMEOUT, APP_NAME
except ImportError as e:
    logging.critical(f"Error CRÍTICO importando dependencias compartidas en Office: {e}.", exc_info=True)
    # Fallbacks si las constantes no se pueden importar (esto es solo para que el módulo cargue sin error, pero las funciones fallarán si las constantes no están bien)
    BASE_URL = "https://graph.microsoft.com/v1.0"
    GRAPH_API_DEFAULT_TIMEOUT = 45
    APP_NAME = "EliteDynamicsPro" # Fallback
    # Considera no relanzar el error aquí para permitir que el resto del sistema intente cargar,
    # pero las funciones de este módulo dependerán de estas constantes.
    # raise ImportError(f"No se pudo importar 'hacer_llamada_api' o constantes: {e}") from e

logger = logging.getLogger(f"{APP_NAME}.actions.office")

# ---- FUNCIONES DE WORD (Operaciones básicas a nivel de archivo y contenido vía OneDrive/SharePoint) ----
# Estas funciones asumen que el archivo Word está en el OneDrive del usuario (/me/drive).
# Para archivos en SharePoint, se usarían las funciones de sharepoint_actions.py con rutas de Drive.

def crear_documento_word(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Crea un nuevo documento de Word (.docx) vacío en OneDrive del usuario.

    Args:
        parametros (Dict[str, Any]):
            'nombre_archivo' (str): Nombre del archivo (se añadirá .docx si no está). Requerido.
            'ruta_onedrive' (str, opcional): Carpeta destino en OneDrive (ej. "/Documentos/Reportes"). Default "/".
            'conflict_behavior' (str, opcional): 'rename', 'replace', o 'fail'. Default 'rename'.
        headers (Dict[str, str]): Cabeceras con token.

    Returns:
        Dict[str, Any]: Metadatos del archivo Word creado.
    """
    nombre_archivo: Optional[str] = parametros.get("nombre_archivo")
    ruta_onedrive: str = parametros.get("ruta_onedrive", "/")
    conflict_behavior: str = parametros.get("conflict_behavior", "rename")

    if not nombre_archivo:
        return {"status": "error", "message": "Parámetro 'nombre_archivo' es requerido."}

    if not nombre_archivo.lower().endswith(".docx"):
        nombre_archivo += ".docx"
        logger.debug(f"Añadida extensión .docx al nombre: {nombre_archivo}")

    # Construir path relativo al root de OneDrive del usuario
    clean_folder_path = ruta_onedrive.strip('/')
    target_file_path_in_drive = f"/{nombre_archivo}" if not clean_folder_path else f"/{clean_folder_path}/{nombre_archivo}"

    # El endpoint para crear un archivo vacío por path es /me/drive/root:/path/to/file.docx:/content
    # con un PUT y cuerpo vacío (o casi vacío) y el Content-Type correcto.
    url = f"{BASE_URL}/me/drive/root:{target_file_path_in_drive}:/content"
    params_query = {"@microsoft.graph.conflictBehavior": conflict_behavior}

    upload_headers = headers.copy()
    upload_headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

    logger.info(f"Creando documento Word vacío '{nombre_archivo}' en OneDrive ruta '/{clean_folder_path}'")
    try:
        # PUT con 0 bytes de data para crear archivo vacío. Graph devuelve metadatos.
        word_metadata = hacer_llamada_api("PUT", url, upload_headers, params=params_query, data=b'', timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": word_metadata, "message": f"Documento Word '{nombre_archivo}' creado."}
    except Exception as e:
        logger.error(f"Error creando documento Word '{nombre_archivo}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e)
        status_code = 500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code
            try:
                details = e.response.json()
            except json.JSONDecodeError:
                details = e.response.text
        return {"status": "error", "message": f"Error al crear documento Word: {type(e).__name__}", "http_status": status_code, "details": details}


def reemplazar_contenido_word(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    REEMPLAZA completamente el contenido de un documento Word (.docx) en OneDrive con nuevo contenido.
    El nuevo contenido puede ser texto plano o bytes de un .docx.
    ADVERTENCIA: Si se envía texto plano, se pierde todo el formato original.

    Args:
        parametros (Dict[str, Any]):
            'item_id_o_ruta' (str): ID del archivo Word en OneDrive o ruta relativa (ej. "/Documentos/mi.docx"). Requerido.
            'nuevo_contenido' (Union[str, bytes]): El nuevo contenido. Si es str, se tratará como texto plano.
                                                 Si son bytes, deben ser bytes válidos de un .docx. Requerido.
            'content_type' (str, opcional): 'text/plain' o 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'.
                                           Inferido si no se provee.
        headers (Dict[str, str]): Cabeceras con token.

    Returns:
        Dict[str, Any]: Metadatos del archivo actualizado.
    """
    item_id_o_ruta: Optional[str] = parametros.get("item_id_o_ruta")
    nuevo_contenido: Optional[Union[str, bytes]] = parametros.get("nuevo_contenido")
    content_type_param: Optional[str] = parametros.get("content_type")

    if not item_id_o_ruta or nuevo_contenido is None:
        return {"status": "error", "message": "Parámetros 'item_id_o_ruta' y 'nuevo_contenido' son requeridos."}

    if "/" in item_id_o_ruta: # Asumir que es una ruta
        url = f"{BASE_URL}/me/drive/root:{item_id_o_ruta.strip('/')}:/content"
    else: # Asumir que es un item ID
        url = f"{BASE_URL}/me/drive/items/{item_id_o_ruta}/content"

    upload_headers = headers.copy()
    data_to_send: bytes

    if isinstance(nuevo_contenido, str):
        data_to_send = nuevo_contenido.encode('utf-8')
        upload_headers['Content-Type'] = content_type_param or 'text/plain'
        logger.warning(f"Reemplazando contenido del Word '{item_id_o_ruta}' con texto plano. Se perderá el formato.")
    elif isinstance(nuevo_contenido, bytes):
        data_to_send = nuevo_contenido
        upload_headers['Content-Type'] = content_type_param or 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        logger.info(f"Reemplazando contenido del Word '{item_id_o_ruta}' con bytes de .docx.")
    else:
        return {"status": "error", "message": "'nuevo_contenido' debe ser string (texto plano) o bytes (archivo .docx)."}

    try:
        # Timeout más largo para subida de contenido
        upload_timeout = max(GRAPH_API_DEFAULT_TIMEOUT, int(len(data_to_send) / 1024 / 1024 * 10) + 10) # 10s por MB + 10s
        updated_metadata = hacer_llamada_api("PUT", url, upload_headers, data=data_to_send, timeout=upload_timeout)
        return {"status": "success", "data": updated_metadata, "message": "Contenido de Word reemplazado."}
    except Exception as e:
        logger.error(f"Error reemplazando contenido Word '{item_id_o_ruta}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e)
        status_code = 500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code
            try:
                details = e.response.json()
            except json.JSONDecodeError:
                details = e.response.text
        return {"status": "error", "message": f"Error al reemplazar contenido Word: {type(e).__name__}", "http_status": status_code, "details": details}

def obtener_documento_word_binario(parametros: Dict[str, Any], headers: Dict[str, str]) -> Union[bytes, Dict[str, Any]]:
    """Obtiene el contenido binario (.docx) de un documento de Word desde OneDrive."""
    item_id_o_ruta: Optional[str] = parametros.get("item_id_o_ruta")
    if not item_id_o_ruta:
        return {"status": "error", "message": "Parámetro 'item_id_o_ruta' es requerido."}

    if "/" in item_id_o_ruta:
        url = f"{BASE_URL}/me/drive/root:{item_id_o_ruta.strip('/')}:/content"
    else:
        url = f"{BASE_URL}/me/drive/items/{item_id_o_ruta}/content"

    logger.info(f"Obteniendo contenido binario del Word (OneDrive): '{item_id_o_ruta}'")
    download_timeout = max(GRAPH_API_DEFAULT_TIMEOUT, 120)
    try:
        file_bytes = hacer_llamada_api("GET", url, headers, timeout=download_timeout, expect_json=False, stream=True)
        if isinstance(file_bytes, bytes):
            logger.info(f"Contenido Word '{item_id_o_ruta}' obtenido ({len(file_bytes)} bytes).")
            return file_bytes
        else:
             logger.error(f"Respuesta inesperada al obtener contenido Word: {type(file_bytes)}")
             return {"status": "error", "message": "Error interno al obtener contenido (respuesta helper inesperada)."}
    except Exception as e:
        logger.error(f"Error obteniendo Word '{item_id_o_ruta}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e)
        status_code = 500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code
            try:
                details = e.response.json()
            except json.JSONDecodeError:
                details = e.response.text
            if status_code == 404:
                return {"status": "error", "message": f"Documento Word '{item_id_o_ruta}' no encontrado.", "details": details, "http_status": 404}
        return {"status": "error", "message": f"Error al obtener documento Word: {type(e).__name__}", "http_status": status_code, "details": details}


# ---- FUNCIONES DE EXCEL (Operaciones de Graph API sobre archivos Excel en OneDrive/SharePoint) ----
# Estas funciones necesitan el 'item_id' del archivo Excel en OneDrive o SharePoint.

def crear_libro_excel(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Crea un nuevo libro de Excel (.xlsx) vacío en OneDrive del usuario."""
    nombre_archivo: Optional[str] = parametros.get("nombre_archivo")
    ruta_onedrive: str = parametros.get("ruta_onedrive", "/")
    conflict_behavior: str = parametros.get("conflict_behavior", "rename")

    if not nombre_archivo:
        return {"status": "error", "message": "Parámetro 'nombre_archivo' es requerido."}
    if not nombre_archivo.lower().endswith(".xlsx"):
        nombre_archivo += ".xlsx"

    clean_folder_path = ruta_onedrive.strip('/')
    target_file_path_in_drive = f"/{nombre_archivo}" if not clean_folder_path else f"/{clean_folder_path}/{nombre_archivo}"
    url = f"{BASE_URL}/me/drive/root:{target_file_path_in_drive}:/content"
    params_query = {"@microsoft.graph.conflictBehavior": conflict_behavior}
    upload_headers = headers.copy()
    upload_headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    logger.info(f"Creando libro Excel vacío '{nombre_archivo}' en OneDrive ruta '/{clean_folder_path}'")
    try:
        excel_metadata = hacer_llamada_api("PUT", url, upload_headers, params=params_query, data=b'', timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": excel_metadata, "message": f"Libro Excel '{nombre_archivo}' creado."}
    except Exception as e:
        logger.error(f"Error creando libro Excel '{nombre_archivo}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e)
        status_code = 500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code
            try:
                details = e.response.json()
            except json.JSONDecodeError:
                details = e.response.text
        return {"status": "error", "message": f"Error al crear libro Excel: {type(e).__name__}", "http_status": status_code, "details": details}

def leer_celda_excel(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Lee valor, texto, fórmulas de una celda/rango en una hoja de Excel."""
    item_id: Optional[str] = parametros.get("item_id") # ID del archivo Excel en OneDrive/SP
    hoja_nombre_o_id: Optional[str] = parametros.get("hoja")
    celda_o_rango_direccion: Optional[str] = parametros.get("celda_o_rango") # Ej: "A1" o "A1:C5"
    drive_prefix = parametros.get("drive_prefix", f"{BASE_URL}/me/drive") # Permite especificar /drives/{id}

    if not all([item_id, hoja_nombre_o_id, celda_o_rango_direccion]):
        return {"status": "error", "message": "Params 'item_id', 'hoja', y 'celda_o_rango' requeridos."}

    url = f"{drive_prefix}/items/{item_id}/workbook/worksheets/{hoja_nombre_o_id}/range(address='{celda_o_rango_direccion}')"
    params_query = {"$select": "text,values,address,formulas,cellCount,columnCount,rowCount"}

    logger.info(f"Leyendo Excel item '{item_id}', hoja '{hoja_nombre_o_id}', rango '{celda_o_rango_direccion}'")
    try:
        range_data = hacer_llamada_api("GET", url, headers, params=params_query, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": range_data}
    except Exception as e:
        logger.error(f"Error leyendo celda/rango Excel: {type(e).__name__} - {e}", exc_info=True)
        details = str(e)
        status_code = 500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code
            try:
                details = e.response.json()
            except json.JSONDecodeError:
                details = e.response.text
        return {"status": "error", "message": f"Error al leer celda/rango Excel: {type(e).__name__}", "http_status": status_code, "details": details}

def escribir_celda_excel(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Escribe valor(es) en una celda o rango de una hoja de Excel."""
    item_id: Optional[str] = parametros.get("item_id")
    hoja_nombre_o_id: Optional[str] = parametros.get("hoja")
    celda_o_rango_direccion: Optional[str] = parametros.get("celda_o_rango")
    valores: Optional[List[List[Any]]] = parametros.get("valores")
    drive_prefix = parametros.get("drive_prefix", f"{BASE_URL}/me/drive")

    if not all([item_id, hoja_nombre_o_id, celda_o_rango_direccion, valores]):
        return {"status": "error", "message": "Params 'item_id', 'hoja', 'celda_o_rango', y 'valores' (List[List]) requeridos."}
    if not isinstance(valores, list) or not all(isinstance(row, list) for row in valores):
        return {"status": "error", "message": "'valores' debe ser una lista de listas."}

    url = f"{drive_prefix}/items/{item_id}/workbook/worksheets/{hoja_nombre_o_id}/range(address='{celda_o_rango_direccion}')"
    body = {"values": valores}

    logger.info(f"Escribiendo en Excel item '{item_id}', hoja '{hoja_nombre_o_id}', rango '{celda_o_rango_direccion}'")
    try:
        updated_range = hacer_llamada_api("PATCH", url, headers, json_data=body, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": updated_range, "message": "Celda/rango actualizado."}
    except Exception as e:
        logger.error(f"Error escribiendo en celda/rango Excel: {type(e).__name__} - {e}", exc_info=True)
        details = str(e)
        status_code = 500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code
            try:
                details = e.response.json()
            except json.JSONDecodeError:
                details = e.response.text
        return {"status": "error", "message": f"Error al escribir en Excel: {type(e).__name__}", "http_status": status_code, "details": details}

def crear_tabla_excel(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Crea una tabla en Excel sobre un rango de datos existente."""
    item_id: Optional[str] = parametros.get("item_id")
    hoja_nombre_o_id: Optional[str] = parametros.get("hoja")
    rango_direccion: Optional[str] = parametros.get("rango") # Ej: "A1:C5"
    tiene_headers_tabla: bool = str(parametros.get("tiene_headers_tabla", "false")).lower() == "true"
    nombre_tabla: Optional[str] = parametros.get("nombre_tabla") # Opcional, Graph puede generarlo
    drive_prefix = parametros.get("drive_prefix", f"{BASE_URL}/me/drive")

    if not all([item_id, hoja_nombre_o_id, rango_direccion]):
        return {"status": "error", "message": "Params 'item_id', 'hoja', y 'rango' requeridos."}
    if ':' not in rango_direccion: # Validación simple de rango
        return {"status": "error", "message": "Formato de 'rango' inválido. Use notación A1 (ej. 'A1:C5')."}

    url = f"{drive_prefix}/items/{item_id}/workbook/worksheets/{hoja_nombre_o_id}/tables/add"
    body: Dict[str, Any] = {"address": f"{hoja_nombre_o_id}!{rango_direccion}", "hasHeaders": tiene_headers_tabla}
    if nombre_tabla:
        body["name"] = nombre_tabla

    logger.info(f"Creando tabla Excel en item '{item_id}', hoja '{hoja_nombre_o_id}', rango '{rango_direccion}'")
    try:
        table_info = hacer_llamada_api("POST", url, headers, json_data=body, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": table_info, "message": "Tabla creada exitosamente."}
    except Exception as e:
        logger.error(f"Error creando tabla Excel: {type(e).__name__} - {e}", exc_info=True)
        details = str(e)
        status_code = 500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code
            try:
                details = e.response.json()
            except json.JSONDecodeError:
                details = e.response.text
        return {"status": "error", "message": f"Error al crear tabla Excel: {type(e).__name__}", "http_status": status_code, "details": details}

def agregar_filas_tabla_excel(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Agrega filas de datos al final de una tabla de Excel."""
    item_id: Optional[str] = parametros.get("item_id")
    tabla_nombre_o_id: Optional[str] = parametros.get("tabla_nombre_o_id")
    valores_filas: Optional[List[List[Any]]] = parametros.get("valores_filas")
    hoja_nombre_o_id: Optional[str] = parametros.get("hoja") # Necesario si se usa nombre de tabla
    drive_prefix = parametros.get("drive_prefix", f"{BASE_URL}/me/drive")

    if not all([item_id, tabla_nombre_o_id, valores_filas]):
        return {"status": "error", "message": "Params 'item_id', 'tabla_nombre_o_id', y 'valores_filas' (List[List]) requeridos."}
    if not isinstance(valores_filas, list) or not all(isinstance(row, list) for row in valores_filas):
        return {"status": "error", "message": "'valores_filas' debe ser una lista de listas."}

    if hoja_nombre_o_id: # Si se usa nombre de tabla, se necesita la hoja
        url = f"{drive_prefix}/items/{item_id}/workbook/worksheets/{hoja_nombre_o_id}/tables/{tabla_nombre_o_id}/rows"
    else: # Si se usa ID de tabla, la hoja no es necesaria en el endpoint
        url = f"{drive_prefix}/items/{item_id}/workbook/tables/{tabla_nombre_o_id}/rows"

    body = {"values": valores_filas}

    logger.info(f"Agregando {len(valores_filas)} filas a tabla Excel '{tabla_nombre_o_id}' en item '{item_id}'")
    try:
        added_rows_info = hacer_llamada_api("POST", url, headers, json_data=body, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": added_rows_info, "message": f"{len(valores_filas)} fila(s) agregada(s) a la tabla."}
    except Exception as e:
        logger.error(f"Error agregando filas a tabla Excel: {type(e).__name__} - {e}", exc_info=True)
        details = str(e)
        status_code = 500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code
            try:
                details = e.response.json()
            except json.JSONDecodeError:
                details = e.response.text
        return {"status": "error", "message": f"Error al agregar filas a tabla: {type(e).__name__}", "http_status": status_code, "details": details}

# --- FIN DEL MÓDULO actions/office_actions.py ---