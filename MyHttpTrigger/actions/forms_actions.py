# MyHttpTrigger/actions/forms_actions.py
import logging
import requests # Solo para tipos de excepción
import json
from typing import Dict, List, Optional, Any

# Importar helper y constantes
try:
    from ..shared.helpers.http_client import hacer_llamada_api
    from ..shared.constants import BASE_URL, GRAPH_API_DEFAULT_TIMEOUT, APP_NAME
except ImportError as e:
    logging.critical(f"Error CRÍTICO importando dependencias compartidas en Forms: {e}.", exc_info=True)
    BASE_URL = "https://graph.microsoft.com/v1.0"
    GRAPH_API_DEFAULT_TIMEOUT = 60 # Timeout un poco más largo para búsquedas
    APP_NAME = "EliteDynamicsPro" # Fallback
    raise ImportError(f"No se pudo importar 'hacer_llamada_api' o constantes: {e}") from e

logger = logging.getLogger(f"{APP_NAME}.actions.forms")

# ---- FUNCIONES DE ACCIÓN PARA MICROSOFT FORMS (vía búsqueda en Drive) ----
# Requieren permisos delegados como Files.Read.All o Sites.Read.All dependiendo del scope

def listar_formularios_en_drive(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Busca archivos que podrían ser Microsoft Forms (.form) en OneDrive del usuario o en un Drive de SharePoint.
    NOTA: Esto devuelve metadatos de archivo, no contenido del formulario ni respuestas.

    Args:
        parametros (Dict[str, Any]):
            'drive_scope' (str, opcional): 'me' (para OneDrive) o 'site'. Default 'me'.
            'site_id' (str, opcional): Requerido si drive_scope es 'site'. ID del sitio de SharePoint.
            'drive_id_or_name' (str, opcional): Requerido si drive_scope es 'site'. ID o nombre de la biblioteca.
            'query' (str, opcional): Término de búsqueda adicional. Default busca por extensión o tipo.
            'top' (int, opcional): Máximo número de resultados. Default 25.
        headers (Dict[str, str]): Cabeceras con token OBO.

    Returns:
        Dict[str, Any]: {"status": "success", "data": [lista_driveItems]} o error.
    """
    drive_scope: str = parametros.get('drive_scope', 'me').lower()
    query: Optional[str] = parametros.get('query')
    top: int = min(int(parametros.get('top', 25)), 200) # Límite para search

    # Construir query de búsqueda si no se proporciona una específica
    # Buscar por extensión .form o por tipo de archivo si es posible (depende de indexación)
    # Esta query puede necesitar ajustes. Podría buscar por 'contentType:Form' si está indexado.
    final_query = query if query else "filetype:form OR contentType:Form" # Intentar buscar por extensión o tipo

    if drive_scope == 'me':
        search_url = f"{BASE_URL}/me/drive/root/search(q='{final_query}')"
        log_loc = "OneDrive del usuario"
    elif drive_scope == 'site':
        site_id: Optional[str] = parametros.get('site_id')
        drive_id_or_name: Optional[str] = parametros.get('drive_id_or_name')
        if not site_id or not drive_id_or_name:
            return {"status": "error", "message": "Si 'drive_scope' es 'site', se requieren 'site_id' y 'drive_id_or_name'."}
        search_url = f"{BASE_URL}/sites/{site_id}/drives/{drive_id_or_name}/root/search(q='{final_query}')"
        log_loc = f"Drive '{drive_id_or_name}' en sitio '{site_id}'"
    else:
        return {"status": "error", "message": "'drive_scope' debe ser 'me' o 'site'."}

    # Parámetros adicionales para la búsqueda (Graph no soporta $skip en search)
    params_query = {'$top': top}

    logger.info(f"Buscando formularios (query='{final_query}') en {log_loc}")
    try:
        # La API de búsqueda puede devolver directamente la lista en 'value' o un objeto con 'hitsContainers'
        search_results = hacer_llamada_api("GET", search_url, headers, params=params_query, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        
        items_found = []
        if isinstance(search_results, dict):
            # Estructura anidada común en /search
            hits_containers = search_results.get('value', []) 
            if isinstance(hits_containers, list):
                 for container in hits_containers:
                     if isinstance(container, dict) and 'hits' in container:
                          hits = container.get('hits', [])
                          if isinstance(hits, list):
                              for hit in hits:
                                   if isinstance(hit, dict) and 'resource' in hit:
                                       items_found.append(hit['resource']) # Añadir el DriveItem encontrado
            else: # A veces /search devuelve value directamente
                 items_found = search_results.get('value', []) if isinstance(search_results.get('value'), list) else []

        logger.info(f"Se encontraron {len(items_found)} posibles archivos de formulario.")
        return {"status": "success", "data": items_found, "message": "Nota: Solo se listan archivos, no se accede al contenido del formulario."}
    except Exception as e:
        logger.error(f"Error buscando formularios en {log_loc}: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al buscar formularios: {type(e).__name__}", "http_status": status_code, "details": details}


# --- Acción NO IMPLEMENTADA Directamente ---
def obtener_respuestas_formulario(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    NOTA IMPORTANTE: Obtener respuestas de Microsoft Forms directamente vía API Graph
    NO está soportado actualmente de forma general.

    La forma recomendada es usar Power Automate:
    1. Crear un flujo que se dispare con "Cuando se envía una respuesta nueva" de Forms.
    2. Usar la acción "Obtener los detalles de la respuesta".
    3. Enviar los detalles obtenidos a esta Azure Function (EliteDynamicsPro) mediante
       una acción "HTTP" en Power Automate (haciendo un POST a nuestro endpoint /dynamics
       con una acción específica como 'procesar_respuesta_form' y el cuerpo JSON adecuado).

    Esta función se deja como placeholder para indicar la limitación.
    """
    form_id = parametros.get("form_id")
    logger.error(f"ACCIÓN NO SOPORTADA DIRECTAMENTE: obtener_respuestas_formulario para Form ID '{form_id}'. "
                 "Se requiere integración con Power Automate (trigger 'Cuando se envía una respuesta nueva' + "
                 "acción 'Obtener los detalles de la respuesta' + llamada HTTP a esta función).")
    return {
        "status": "error",
        "message": "Acción no soportada directamente por API Graph.",
        "details": "La obtención de respuestas de Forms requiere un flujo de Power Automate que envíe los datos a esta función."
    }

# --- FIN DEL MÓDULO actions/forms_actions.py ---