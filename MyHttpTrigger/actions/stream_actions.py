# MyHttpTrigger/actions/stream_actions.py
import logging
import requests # Para requests.exceptions.HTTPError
from typing import Dict, List, Optional, Any

# Importar el cliente autenticado y las constantes
from ..shared.helpers.http_client import AuthenticatedHttpClient
from ..shared import constants

# Asumimos que sharepoint_actions será refactorizado para que _obtener_site_id_sp use AuthenticatedHttpClient
try:
    from ..actions.sharepoint_actions import _obtener_site_id_sp
except ImportError:
    logger.error("No se pudo importar '_obtener_site_id_sp' de sharepoint_actions. Las funciones de Stream que dependen de él podrían fallar.")
    # Definir un placeholder si la importación falla para evitar errores de carga, aunque las funciones fallarán.
    def _obtener_site_id_sp(client: AuthenticatedHttpClient, params: Dict[str, Any], id_type_preference: str = "id") -> str:
        raise NotImplementedError("Helper _obtener_site_id_sp no está disponible.")

logger = logging.getLogger(__name__)

# Timeout más largo para búsquedas o descargas de video si es necesario
VIDEO_ACTION_TIMEOUT = max(constants.DEFAULT_API_TIMEOUT, 120) # Ej. 2 minutos

# ---- FUNCIONES DE ACCIÓN PARA VIDEOS (Stream on SharePoint/OneDrive) ----
# Requieren permisos delegados como Files.Read.All, Sites.Read.All

def listar_videos(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Busca archivos de video (.mp4, .mov, etc.) en OneDrive del usuario o en un Drive de SharePoint.
    Devuelve metadatos de archivo (DriveItems).
    """
    drive_scope: str = params.get('drive_scope', 'me').lower()
    search_folder_path: str = params.get('search_folder_path', '/') # Ruta de la carpeta donde buscar, ej: "/Videos"
    user_query: Optional[str] = params.get('query') # Query adicional del usuario
    top: int = min(int(params.get('top', 25)), 200) # Límite para search API

    # Construir query de búsqueda base para tipos comunes de video
    video_file_types_filter = "filetype:mp4 OR filetype:mov OR filetype:wmv OR filetype:avi OR filetype:mkv OR filetype:webm"
    # contentType podría ser más específico si la indexación es buena, ej: contentType:Video
    
    final_search_query = f"({video_file_types_filter})"
    if user_query:
        final_search_query = f"({user_query}) AND ({video_file_types_filter})"

    search_base_url_segment: str
    log_location_description: str

    try:
        if drive_scope == 'me':
            drive_id = params.get("drive_id") # Opcional, para un drive específico del usuario
            if drive_id:
                search_base_url_segment = f"/me/drives/{drive_id}/root"
                if search_folder_path and search_folder_path != '/':
                    search_base_url_segment += f":{search_folder_path.strip('/')}:"
                log_location_description = f"Drive '{drive_id}' del usuario (carpeta: '{search_folder_path}')"
            else: # Drive por defecto del usuario
                search_base_url_segment = "/me/drive/root"
                if search_folder_path and search_folder_path != '/':
                    search_base_url_segment += f":{search_folder_path.strip('/')}:"
                log_location_description = f"OneDrive del usuario (carpeta: '{search_folder_path}')"
        elif drive_scope == 'site':
            # _obtener_site_id_sp debería devolver el ID del sitio.
            # Se necesita también el drive_id para el sitio.
            site_id = _obtener_site_id_sp(client, params) # Pasamos client y params
            drive_id: Optional[str] = params.get('drive_id')
            if not drive_id: # drive_id es esencial para especificar la biblioteca en un sitio
                return {"status": "error", "message": "Si 'drive_scope' es 'site', se requiere 'drive_id' (ID de la biblioteca).", "http_status": 400}
            
            search_base_url_segment = f"/sites/{site_id}/drives/{drive_id}/root"
            if search_folder_path and search_folder_path != '/':
                 search_base_url_segment += f":{search_folder_path.strip('/')}:"
            log_location_description = f"Drive '{drive_id}' en sitio '{site_id}' (carpeta: '{search_folder_path}')"
        else:
            return {"status": "error", "message": "'drive_scope' debe ser 'me' o 'site'.", "http_status": 400}
    except ValueError as ve: # Error de _obtener_site_id_sp (ej. sitio no encontrado)
        return {"status": "error", "message": f"Error determinando sitio/drive para búsqueda de videos: {ve}", "http_status": 400}
    except Exception as path_err:
        logger.error(f"Error construyendo ruta de búsqueda para videos: {path_err}", exc_info=True)
        return {"status": "error", "message": "Error interno construyendo ruta de búsqueda de videos."}

    # El endpoint es /search(q='{queryText}')
    search_api_url = f"{constants.GRAPH_API_BASE_URL}{search_base_url_segment}/search(q='{final_search_query}')"
    api_params_query = {
        '$top': top, 
        '$select': 'id,name,webUrl,video,size,file,createdDateTime,lastModifiedDateTime,parentReference'
    }

    logger.info(f"Buscando videos (Query='{final_search_query}') en {log_location_description}")
    try:
        response = client.get(url=search_api_url, scope=constants.GRAPH_SCOPE, params=api_params_query, timeout=VIDEO_ACTION_TIMEOUT)
        search_results = response.json()
        
        items_found: List[Dict[str, Any]] = []
        # La respuesta de /search puede tener los resultados en 'value' o anidados en 'value[].hits[].resource'
        if 'value' in search_results:
            for hit_container in search_results['value']:
                if isinstance(hit_container, dict) and 'hits' in hit_container: # Estructura anidada
                    for hit in hit_container.get('hits', []):
                        if isinstance(hit, dict) and 'resource' in hit and isinstance(hit['resource'], dict) and hit['resource'].get('video'):
                            items_found.append(hit['resource'])
                elif isinstance(hit_container, dict) and hit_container.get('video'): # Lista plana de DriveItems con faceta video
                     items_found.append(hit_container)

        logger.info(f"Se encontraron {len(items_found)} archivos de video en {log_location_description}.")
        return {"status": "success", "data": items_found, "total_retrieved": len(items_found)}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP buscando videos en {log_location_description}: {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error buscando videos en {log_location_description}: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al buscar videos: {type(e).__name__}", "details": str(e), "http_status": 500}


def obtener_metadatos_video(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Obtiene los metadatos de un archivo de video (DriveItem), incluyendo la faceta 'video'.
    """
    item_id: Optional[str] = params.get("item_id")
    drive_id: Optional[str] = params.get("drive_id") # ID del Drive donde está el item
    site_id: Optional[str] = params.get("site_id")   # Opcional, si el drive es de un sitio
    select_fields: Optional[str] = params.get('select', "id,name,webUrl,size,createdDateTime,lastModifiedDateTime,file,video,parentReference,@microsoft.graph.downloadUrl")

    if not item_id or not drive_id:
        return {"status": "error", "message": "Parámetros 'item_id' y 'drive_id' son requeridos.", "http_status": 400}

    item_url: str
    log_location_description: str

    if site_id:
        item_url = f"{constants.GRAPH_API_BASE_URL}/sites/{site_id}/drives/{drive_id}/items/{item_id}"
        log_location_description = f"Drive '{drive_id}' en sitio '{site_id}'"
    else: # Asumir OneDrive del usuario
        item_url = f"{constants.GRAPH_API_BASE_URL}/me/drives/{drive_id}/items/{item_id}"
        log_location_description = f"Drive '{drive_id}' del usuario"
    
    api_params_query = {"$select": select_fields}
    if "video" not in select_fields.lower(): # Asegurar que se expande si no está en select
         api_params_query["$expand"] = "video"


    logger.info(f"Obteniendo metadatos de video para item '{item_id}' en {log_location_description}")
    try:
        response = client.get(url=item_url, scope=constants.GRAPH_SCOPE, params=api_params_query, timeout=constants.DEFAULT_API_TIMEOUT)
        video_metadata = response.json()
        
        if not video_metadata.get('video') and not video_metadata.get('file', {}).get('mimeType','').startswith('video/'):
             logger.warning(f"Item '{item_id}' obtenido, pero podría no ser un video (falta faceta 'video' o MIME type de video).")
             return {"status": "warning", "data": video_metadata, "message": "Metadatos obtenidos, pero el item podría no ser un video."}
        
        return {"status": "success", "data": video_metadata}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP obteniendo metadatos video '{item_id}': {status_code_resp} - {error_details[:300]}", exc_info=False)
        if status_code_resp == 404:
            return {"status": "error", "message": f"Video con ID '{item_id}' no encontrado en {log_location_description}.", "http_status": 404, "details": error_details}
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error obteniendo metadatos video '{item_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al obtener metadatos de video: {type(e).__name__}", "details": str(e), "http_status": 500}

def get_video_playback_url(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Obtiene una URL de descarga para un archivo de video, que a menudo se puede usar para reproducción.
    """
    item_id: Optional[str] = params.get("item_id")
    drive_id: Optional[str] = params.get("drive_id")
    site_id: Optional[str] = params.get("site_id")

    if not item_id or not drive_id:
        return {"status": "error", "message": "Parámetros 'item_id' y 'drive_id' son requeridos.", "http_status": 400}

    # Primero, obtenemos los metadatos del video para asegurar que existe y para obtener @microsoft.graph.downloadUrl
    # Podríamos llamar a obtener_metadatos_video, pero para ser autocontenida:
    
    item_url_base: str
    log_location_description: str
    if site_id:
        item_url_base = f"{constants.GRAPH_API_BASE_URL}/sites/{site_id}/drives/{drive_id}/items/{item_id}"
        log_location_description = f"item '{item_id}' en drive '{drive_id}', sitio '{site_id}'"
    else:
        item_url_base = f"{constants.GRAPH_API_BASE_URL}/me/drives/{drive_id}/items/{item_id}"
        log_location_description = f"item '{item_id}' en drive '{drive_id}' del usuario"

    # Solicitamos explícitamente la URL de descarga
    api_params_query = {'$select': 'id,name,webUrl,@microsoft.graph.downloadUrl,file,video'}

    logger.info(f"Obteniendo URL de reproducción/descarga para video: {log_location_description}")
    try:
        response = client.get(url=item_url_base, scope=constants.GRAPH_SCOPE, params=api_params_query, timeout=constants.DEFAULT_API_TIMEOUT)
        item_data = response.json()

        download_url = item_data.get("@microsoft.graph.downloadUrl")
        
        if not download_url:
            logger.warning(f"No se encontró '@microsoft.graph.downloadUrl' para el video '{item_id}'. El item podría no ser accesible o no ser un archivo.")
            return {"status": "error", "message": f"No se pudo obtener la URL de descarga para el video '{item_id}'.", "details": "La propiedad @microsoft.graph.downloadUrl no está presente.", "data": item_data}

        # Adicionalmente, se podría verificar la faceta 'video' para otras URLs o información, pero downloadUrl es lo más directo.
        # "video": { "bitrate": ..., "duration": ..., "height": ..., "width": ..., "audioBitsPerSample": ..., "audioChannels": ..., "audioFormat": ..., "audioSamplesPerSecond": ..., "fourCC": ... }
        # No suele tener URLs de streaming directo en esta faceta.
        
        logger.info(f"URL de descarga obtenida para video '{item_id}': {download_url[:100]}...") # Loguear solo una parte
        return {"status": "success", "data": {"id": item_id, "name": item_data.get("name"), "webUrl": item_data.get("webUrl"), "playback_url": download_url, "video_info": item_data.get("video"), "file_info": item_data.get("file") }}

    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP obteniendo URL de video '{item_id}': {status_code_resp} - {error_details[:300]}", exc_info=False)
        if status_code_resp == 404:
            return {"status": "error", "message": f"Video '{item_id}' no encontrado.", "http_status": 404, "details": error_details}
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error obteniendo URL de video '{item_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al obtener URL de video: {type(e).__name__}", "details": str(e), "http_status": 500}


def obtener_transcripcion_video(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    NOTA IMPORTANTE: Obtener/generar transcripciones de videos almacenados en
    OneDrive/SharePoint directamente vía API Graph NO está soportado de forma fiable y estándar.

    Si el servicio de Stream (on SharePoint) genera automáticamente un archivo de
    transcripción (ej. VTT) junto al video, se podría intentar buscar y descargar
    ese archivo usando las acciones de OneDrive/SharePoint (ej. onedrive_actions.download_file).

    Alternativamente, se puede usar Power Automate con conectores de Stream o Azure Video Indexer
    para obtener o generar transcripciones y luego enviar el resultado a esta función/endpoint.

    Esta función es un placeholder para indicar la limitación.
    El 'client' se incluye por consistencia.
    """
    video_item_id = params.get("item_id") # ID del archivo de video
    log_message = (
        f"Intento de obtener transcripción para video '{video_item_id}'. Esta acción NO está soportada directamente por API Graph. "
        "Se debe buscar un archivo VTT asociado (si existe) o usar Power Automate / Azure Video Indexer."
    )
    logger.warning(log_message)
    return {
        "status": "not_supported",
        "message": "La obtención/generación de transcripciones de video no es una función directa de API Graph para archivos.",
        "details": (
            "Para obtener transcripciones: "
            "1. Verifique si un archivo de transcripción (ej. .vtt) existe junto al video en OneDrive/SharePoint y descárguelo usando las acciones de archivo. "
            "2. Use servicios como Power Automate (con el conector de Stream si el video está en Stream clásico o el nuevo Stream) o Azure Video Indexer para procesar el video y obtener la transcripción. "
            "Luego, los resultados pueden ser enviados a esta Azure Function."
        ),
        "http_status": 501 # Not Implemented
    }

# --- FIN DEL MÓDULO actions/stream_actions.py ---