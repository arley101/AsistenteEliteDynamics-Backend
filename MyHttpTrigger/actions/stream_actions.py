# MyHttpTrigger/actions/stream_actions.py
import logging
import requests # Solo para tipos de excepción
import json
from typing import Dict, List, Optional, Any

# Importar helper y constantes
try:
    from ..shared.helpers.http_client import hacer_llamada_api
    # Reutilizar la función _obtener_site_id_sp de sharepoint si se busca en sitios
    # O duplicarla/adaptarla aquí si preferimos mantener módulos independientes
    from ..actions.sharepoint_actions import _obtener_site_id_sp # Asumiendo que está disponible y refactorizada
    from ..shared.constants import BASE_URL, GRAPH_API_DEFAULT_TIMEOUT, APP_NAME
except ImportError as e:
    logging.critical(f"Error CRÍTICO importando dependencias compartidas/SP en Stream: {e}.", exc_info=True)
    BASE_URL = "https://graph.microsoft.com/v1.0"
    GRAPH_API_DEFAULT_TIMEOUT = 60
    APP_NAME = "EliteDynamicsPro" # Fallback
    # Definir un _obtener_site_id_sp dummy o lanzar error
    def _obtener_site_id_sp(*args, **kwargs): raise NotImplementedError("Helper _obtener_site_id_sp no importado.")
    raise ImportError(f"No se pudo importar 'hacer_llamada_api', constantes o helpers de SP: {e}") from e

logger = logging.getLogger(f"{APP_NAME}.actions.stream")

# Timeout más largo para búsquedas
SEARCH_TIMEOUT = max(GRAPH_API_DEFAULT_TIMEOUT, 120)

# ---- FUNCIONES DE ACCIÓN PARA VIDEOS (Stream on SharePoint) ----
# Requieren permisos delegados como Files.Read.All, Sites.Read.All

def listar_videos(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Busca archivos de video (.mp4, .mov, etc.) en OneDrive del usuario o en un Drive de SharePoint.

    Args:
        parametros (Dict[str, Any]):
            'drive_scope' (str, opcional): 'me' (OneDrive) o 'site'. Default 'me'.
            'site_id' (str, opcional): Requerido si drive_scope es 'site'.
            'drive_id_or_name' (str, opcional): Requerido si drive_scope es 'site'.
            'ruta_carpeta' (str, opcional): Carpeta específica donde buscar (relativa a la raíz del drive). Default '/'.
            'query' (str, opcional): Término de búsqueda adicional (además del filtro por tipo de video).
            'top' (int, opcional): Máximo número de resultados. Default 25.
        headers (Dict[str, str]): Cabeceras con token OBO.

    Returns:
        Dict[str, Any]: {"status": "success", "data": [lista_driveItems_video]} o error.
    """
    drive_scope: str = parametros.get('drive_scope', 'me').lower()
    ruta_carpeta: str = parametros.get('ruta_carpeta', '/')
    query: Optional[str] = parametros.get('query')
    top: int = min(int(parametros.get('top', 25)), 200) # Límite para search

    # Construir query de búsqueda base para tipos comunes de video
    video_filter = "filetype:mp4 OR filetype:mov OR filetype:wmv OR filetype:avi OR filetype:mkv"
    final_query = f"({video_filter})"
    if query:
        final_query = f"({query}) AND ({video_filter})" # Combina query del usuario con filtro de video

    search_base_url: str
    log_loc: str

    try:
        if drive_scope == 'me':
            # Buscar dentro de una carpeta específica en OneDrive
            item_endpoint = f"{BASE_URL}/me/drive/root"
            if ruta_carpeta != '/':
                 item_endpoint += f":{ruta_carpeta.strip('/')}:"
            search_url = f"{item_endpoint}/search(q='{final_query}')"
            log_loc = f"OneDrive ('{ruta_carpeta}')"
        elif drive_scope == 'site':
            site_id = _obtener_site_id_sp(parametros, headers) # Reutiliza helper de SP
            drive_id_or_name: Optional[str] = parametros.get('drive_id_or_name')
            if not drive_id_or_name: return {"status": "error", "message": "Si 'drive_scope' es 'site', se requiere 'drive_id_or_name'."}
            
            item_endpoint = f"{BASE_URL}/sites/{site_id}/drives/{drive_id_or_name}/root"
            if ruta_carpeta != '/':
                item_endpoint += f":{ruta_carpeta.strip('/')}:"
            search_url = f"{item_endpoint}/search(q='{final_query}')"
            log_loc = f"Drive '{drive_id_or_name}' sitio '{site_id}' ('{ruta_carpeta}')"
        else:
            return {"status": "error", "message": "'drive_scope' debe ser 'me' o 'site'."}
    except ValueError as ve: # Error de _obtener_site_id_sp
        return {"status": "error", "message": f"Error determinando sitio/drive: {ve}"}
    except Exception as path_err:
        logger.error(f"Error construyendo ruta de búsqueda Stream: {path_err}", exc_info=True)
        return {"status": "error", "message": "Error interno construyendo ruta de búsqueda."}


    params_query = {'$top': top, '$select': 'id,name,webUrl,video,size,file,createdDateTime,lastModifiedDateTime'} # Incluir faceta video

    logger.info(f"Buscando videos (Query='{final_query}') en {log_loc}")
    try:
        search_results = hacer_llamada_api("GET", search_url, headers, params=params_query, timeout=SEARCH_TIMEOUT)
        
        items_found = []
        if isinstance(search_results, dict):
            hits_containers = search_results.get('value', [])
            if isinstance(hits_containers, list):
                 for container in hits_containers:
                     if isinstance(container, dict) and 'hits' in container:
                          hits = container.get('hits', [])
                          if isinstance(hits, list):
                              for hit in hits:
                                   if isinstance(hit, dict) and 'resource' in hit:
                                       # Filtrar para asegurar que realmente sea un archivo con faceta de video (a veces search devuelve carpetas)
                                       resource = hit['resource']
                                       if isinstance(resource, dict) and resource.get('video'):
                                            items_found.append(resource)
            else: # Si devuelve 'value' directamente
                 potential_items = search_results.get('value', [])
                 if isinstance(potential_items, list):
                      items_found = [item for item in potential_items if isinstance(item, dict) and item.get('video')]

        logger.info(f"Se encontraron {len(items_found)} archivos de video en {log_loc}.")
        return {"status": "success", "data": items_found}
    except Exception as e:
        logger.error(f"Error buscando videos en {log_loc}: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al buscar videos: {type(e).__name__}", "http_status": status_code, "details": details}


def obtener_metadatos_video(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Obtiene los metadatos de un archivo de video, incluyendo la faceta 'video'.

    Args:
        parametros (Dict[str, Any]):
            'item_id' (str): ID del DriveItem del video. Requerido.
            'drive_scope' (str, opcional): 'me' (OneDrive) o 'site'. Default 'me'.
            'site_id' (str, opcional): Requerido si drive_scope es 'site'.
            'drive_id_or_name' (str, opcional): Requerido si drive_scope es 'site'.
             'select' (str, opcional): Campos adicionales a seleccionar. '$expand=video' se añade siempre.
        headers (Dict[str, str]): Cabeceras con token OBO.

    Returns:
        Dict[str, Any]: {"status": "success", "data": {driveItem_con_video_facet}} o error.
    """
    item_id: Optional[str] = parametros.get("item_id")
    drive_scope: str = parametros.get('drive_scope', 'me').lower()
    select: Optional[str] = parametros.get('select', "id,name,webUrl,size,createdDateTime,lastModifiedDateTime,file") # Campos base

    if not item_id:
        return {"status": "error", "message": "Parámetro 'item_id' es requerido."}

    item_url_base : str
    log_loc: str

    try:
        if drive_scope == 'me':
            item_url_base = f"{BASE_URL}/me/drive/items/{item_id}"
            log_loc = "OneDrive"
        elif drive_scope == 'site':
            site_id = _obtener_site_id_sp(parametros, headers)
            drive_id_or_name: Optional[str] = parametros.get('drive_id_or_name')
            if not drive_id_or_name: return {"status": "error", "message": "Si 'drive_scope' es 'site', se requiere 'drive_id_or_name'."}
            item_url_base = f"{BASE_URL}/sites/{site_id}/drives/{drive_id_or_name}/items/{item_id}"
            log_loc = f"Drive '{drive_id_or_name}' sitio '{site_id}'"
        else:
            return {"status": "error", "message": "'drive_scope' debe ser 'me' o 'site'."}
    except ValueError as ve: # Error de _obtener_site_id_sp
        return {"status": "error", "message": f"Error determinando sitio/drive: {ve}"}
    except Exception as path_err:
        logger.error(f"Error construyendo ruta para obtener metadatos video: {path_err}", exc_info=True)
        return {"status": "error", "message": "Error interno construyendo ruta."}

    # Asegurar que se incluye y expande la faceta 'video'
    final_select = select if select else ""
    if "video" not in final_select.lower().split(','):
        final_select = f"{final_select},video" if final_select else "video"

    params_query = {"$select": final_select.strip(','), "$expand": "video"}

    logger.info(f"Obteniendo metadatos de video para item '{item_id}' en {log_loc}")
    try:
        video_metadata = hacer_llamada_api("GET", item_url_base, headers, params=params_query, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        # Verificar si realmente tiene la faceta de video
        if isinstance(video_metadata, dict) and not video_metadata.get('video'):
             logger.warning(f"Item '{item_id}' obtenido pero no parece ser un video (falta faceta 'video').")
             # Devolver los metadatos igualmente, pero añadir una nota
             return {"status": "success", "data": video_metadata, "message": "Metadatos obtenidos, pero el item podría no ser un video (falta faceta específica)."}
        elif isinstance(video_metadata, dict):
             return {"status": "success", "data": video_metadata}
        else:
            return {"status": "error", "message": f"Respuesta inesperada al obtener metadatos del video '{item_id}'."}
            
    except Exception as e:
        logger.error(f"Error obteniendo metadatos video '{item_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            if status_code == 404:
                return {"status": "error", "message": f"Video con ID '{item_id}' no encontrado en {log_loc}.", "details": details}
        return {"status": "error", "message": f"Error al obtener metadatos de video: {type(e).__name__}", "http_status": status_code, "details": details}


def obtener_transcripcion_video(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    NOTA IMPORTANTE: Obtener/generar transcripciones de videos almacenados en
    OneDrive/SharePoint directamente vía API Graph NO está soportado de forma fiable.

    Si el servicio de Stream (on SharePoint) genera automáticamente un archivo de
    transcripción (ej. VTT) junto al video, se podría intentar buscar y descargar
    ese archivo usando las acciones de OneDrive/SharePoint.

    Alternativamente, se puede usar Power Automate con conectores de Stream o Azure Video Indexer
    para obtener o generar transcripciones y luego enviar el resultado a esta función.

    Esta función es un placeholder para indicar la limitación.
    """
    video_item_id = parametros.get("item_id") # ID del archivo de video
    logger.error(f"ACCIÓN NO SOPORTADA DIRECTAMENTE: obtener_transcripcion_video para video '{video_item_id}'. "
                 "No hay API Graph estándar para esto. Revisar si existe un archivo .vtt asociado "
                 "o usar Power Automate / Azure Video Indexer.")
    return {
        "status": "error",
        "message": "Acción no soportada directamente por API Graph.",
        "details": "La obtención/generación de transcripciones requiere buscar archivos VTT asociados o usar otros servicios como Power Automate o Azure Video Indexer."
    }

# Las funciones para subir, descargar, mover, copiar, eliminar videos son las mismas
# que para cualquier archivo y deben usarse desde onedrive_actions.py o sharepoint_actions.py

# --- FIN DEL MÓDULO actions/stream_actions.py ---