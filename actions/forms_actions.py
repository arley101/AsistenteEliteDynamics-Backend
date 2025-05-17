# MyHttpTrigger/actions/forms_actions.py
import logging
import requests # Para requests.exceptions.HTTPError
from typing import Dict, List, Optional, Any

# Importar el cliente autenticado y las constantes
from shared.helpers.http_client import AuthenticatedHttpClient
from shared import constants

logger = logging.getLogger(__name__)

# ---- FUNCIONES DE ACCIÓN PARA MICROSOFT FORMS ----
# Estas funciones interactúan con Microsoft Forms principalmente a través de la búsqueda
# de archivos .form en OneDrive o SharePoint, ya que la API Graph directa para
# contenido y respuestas de Forms es limitada.

def list_forms(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Busca archivos que podrían ser Microsoft Forms (.form) en OneDrive del usuario o en un Drive de SharePoint.
    Devuelve metadatos de archivo (DriveItems), no el contenido detallado del formulario ni sus respuestas.

    Args:
        client (AuthenticatedHttpClient): Cliente autenticado para realizar llamadas a Graph API.
        params (Dict[str, Any]): Diccionario de parámetros.
            'drive_scope' (str, opcional): 'me' (para OneDrive del usuario) o 'site'. Default 'me'.
            'site_id' (str, opcional): Requerido si drive_scope es 'site'. ID del sitio de SharePoint.
            'drive_id' (str, opcional): Requerido si drive_scope es 'site'. ID de la biblioteca de documentos (Drive).
            'search_query' (str, opcional): Término de búsqueda adicional. Si no se provee, busca por tipo de archivo Forms.
            'top' (int, opcional): Máximo número de resultados. Default 25. Max 200 para search.

    Returns:
        Dict[str, Any]: {"status": "success", "data": [lista_driveItems]} o {"status": "error", ...}.
    """
    drive_scope: str = params.get('drive_scope', 'me').lower()
    search_text: Optional[str] = params.get('search_query')
    top: int = min(int(params.get('top', 25)), 200) # Graph API search limit

    # Query base para buscar archivos de Forms. La extensión .form no siempre está expuesta en 'filetype'.
    # 'contentType:Form' podría funcionar si el contenido está correctamente indexado.
    # Una búsqueda genérica por nombre o una palabra clave común podría ser más efectiva.
    # Por ahora, usamos un query que intenta encontrar por nombre común o tipo.
    # El usuario puede pasar su propio 'search_query'.
    effective_search_query = search_text if search_text else '"Microsoft Form" OR filetype:form OR contentType:FormPackage'

    api_params: Dict[str, Any] = {'$top': top, '$select': 'id,name,webUrl,createdDateTime,lastModifiedDateTime,size,parentReference,file'}

    search_url_segment: str
    log_location_description: str

    if drive_scope == 'me':
        search_url_segment = "/me/drive/root"
        log_location_description = "OneDrive del usuario"
    elif drive_scope == 'site':
        site_id: Optional[str] = params.get('site_id')
        drive_id: Optional[str] = params.get('drive_id') # Usar drive_id en lugar de drive_id_or_name para consistencia
        if not site_id or not drive_id:
            logger.warning("Para drive_scope 'site', 'site_id' y 'drive_id' son requeridos.")
            return {"status": "error", "message": "Si 'drive_scope' es 'site', se requieren 'site_id' y 'drive_id'.", "http_status": 400}
        search_url_segment = f"/sites/{site_id}/drives/{drive_id}/root"
        log_location_description = f"Drive '{drive_id}' en sitio '{site_id}'"
    else:
        logger.warning(f"Valor de 'drive_scope' inválido: {drive_scope}. Debe ser 'me' o 'site'.")
        return {"status": "error", "message": "'drive_scope' debe ser 'me' o 'site'.", "http_status": 400}

    # El endpoint de búsqueda es /search(q='{queryText}')
    # Es importante URL-encodear el effective_search_query si se interpola directamente.
    # El cliente HTTP de requests usualmente maneja la codificación de los parámetros de query.
    # Sin embargo, para el path segment de search, es mejor no construirlo con f-string directamente.
    # La API de search es un poco particular.
    # Correcto: /search con q en params, o /search(q='text')
    # URL para búsqueda:
    url = f"{constants.GRAPH_API_BASE_URL}{search_url_segment}/search(q='{effective_search_query}')"

    logger.info(f"Buscando formularios (Query='{effective_search_query}') en {log_location_description} (Top: {top})")
    try:
        response = client.get(url=url, scope=constants.GRAPH_SCOPE, params=api_params)
        search_results_data = response.json()
        
        # La respuesta de /search puede tener los resultados en 'value' o anidados en 'value[].hits[].resource'
        items_found: List[Dict[str, Any]] = []
        if 'value' in search_results_data:
            for hit_container in search_results_data['value']:
                if 'hits' in hit_container:
                    for hit in hit_container['hits']:
                        if 'resource' in hit:
                            items_found.append(hit['resource'])
                elif all(k in hit_container for k in ('id', 'name')): # Si es una lista plana de DriveItems
                    items_found.append(hit_container)


        logger.info(f"Se encontraron {len(items_found)} posibles archivos de formulario en {log_location_description}.")
        return {
            "status": "success",
            "data": items_found,
            "message": f"{len(items_found)} posibles formularios encontrados. Nota: Solo se listan archivos, no se accede al contenido del formulario.",
            "total_retrieved": len(items_found)
        }
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"Error HTTP buscando formularios en {log_location_description}: {http_err.response.status_code} - {http_err.response.text[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {http_err.response.status_code}", "details": http_err.response.text, "http_status": http_err.response.status_code}
    except Exception as e:
        logger.error(f"Error buscando formularios en {log_location_description}: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al buscar formularios: {type(e).__name__}", "details": str(e)}


def get_form(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Obtiene los metadatos de un archivo específico que se presume es un Microsoft Form (.form) 
    almacenado en OneDrive o SharePoint, usando su DriveItem ID.
    NOTA: Esto devuelve metadatos del archivo (DriveItem), no la estructura interna del formulario.

    Args:
        client (AuthenticatedHttpClient): Cliente autenticado para realizar llamadas a Graph API.
        params (Dict[str, Any]): Diccionario de parámetros.
            'form_item_id' (str): ID del DriveItem correspondiente al archivo .form. Requerido.
            'drive_id' (str): ID del Drive donde reside el item. Requerido.
            'site_id' (str, opcional): ID del Site de SharePoint, si el Drive no es el del usuario.
                                      Si no se provee, se asume OneDrive del usuario (/me/drive).
            'select' (str, opcional): Campos específicos a seleccionar del DriveItem.

    Returns:
        Dict[str, Any]: {"status": "success", "data": {driveItem_metadata}} o {"status": "error", ...}.
    """
    form_item_id: Optional[str] = params.get("form_item_id")
    drive_id: Optional[str] = params.get("drive_id") # Asumimos que el form_item_id es relativo a un drive
    site_id: Optional[str] = params.get("site_id") # Para identificar si es un drive de sitio o de usuario
    select_fields: Optional[str] = params.get("select")

    if not form_item_id or not drive_id:
        logger.warning("'form_item_id' y 'drive_id' son parámetros requeridos para get_form.")
        return {"status": "error", "message": "Parámetros 'form_item_id' y 'drive_id' son requeridos.", "http_status": 400}

    if site_id:
        # Acceso a un Drive específico dentro de un Site de SharePoint
        url = f"{constants.GRAPH_API_BASE_URL}/sites/{site_id}/drives/{drive_id}/items/{form_item_id}"
        log_target = f"item '{form_item_id}' en drive '{drive_id}' del sitio '{site_id}'"
    else:
        # Acceso a un Drive del usuario (usualmente /me/drive, pero drive_id puede ser otro drive del usuario)
        # Si drive_id es el ID del drive principal del usuario, esto funciona.
        # Podríamos necesitar /me/drives/{drive_id}/items/{form_item_id} si es un drive no principal.
        # Por simplicidad, si no hay site_id, intentamos /me/drive/items/ que es lo más común.
        # Si el drive_id es realmente el ID del drive del usuario, la URL es /me/drives/{drive_id}/items/{item_id}
        # O si es el default: /me/drive/items/{item_id}. Aquí asumimos que `drive_id` es para el path base y `item_id` es el específico.
        # Si el `drive_id` se refiere al drive de /me, entonces la URL es /me/drives/{drive_id}/items/{form_item_id}
        # O, si es el drive por defecto, /me/drive/items/{form_item_id}.
        # Para ser más explícito, si el drive_id es conocido:
        url = f"{constants.GRAPH_API_BASE_URL}/me/drives/{drive_id}/items/{form_item_id}"
        log_target = f"item '{form_item_id}' en drive '{drive_id}' del usuario"


    api_params = {}
    if select_fields:
        api_params['$select'] = select_fields
    else: # Campos por defecto útiles para un archivo
        api_params['$select'] = "id,name,webUrl,createdDateTime,lastModifiedDateTime,size,parentReference,file,package"


    logger.info(f"Obteniendo metadatos del archivo de formulario: {log_target}")
    try:
        response = client.get(url=url, scope=constants.GRAPH_SCOPE, params=api_params if api_params else None)
        form_file_metadata = response.json()
        
        # Comprobar si tiene la faceta 'package' y el tipo 'Form' podría ser útil
        if form_file_metadata.get("package", {}).get("type") == "Form":
             logger.info(f"Metadatos del archivo de Formulario '{form_item_id}' obtenidos. Es un paquete de tipo Form.")
        elif form_file_metadata.get("file"):
             logger.info(f"Metadatos del archivo '{form_item_id}' obtenidos. Confirmar si es un Form por su contenido o nombre.")
        else:
            logger.warning(f"Item '{form_item_id}' obtenido, pero no parece ser un archivo (sin faceta 'file' o 'package').")


        return {"status": "success", "data": form_file_metadata, "message": "Metadatos del archivo de formulario obtenidos."}
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"Error HTTP obteniendo archivo de formulario '{form_item_id}': {http_err.response.status_code} - {http_err.response.text[:200]}", exc_info=False)
        if http_err.response.status_code == 404:
             return {"status": "error", "message": f"Archivo de formulario '{form_item_id}' no encontrado.", "details": http_err.response.text, "http_status": 404}
        return {"status": "error", "message": f"Error HTTP: {http_err.response.status_code}", "details": http_err.response.text, "http_status": http_err.response.status_code}
    except Exception as e:
        logger.error(f"Error obteniendo archivo de formulario '{form_item_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al obtener archivo de formulario: {type(e).__name__}", "details": str(e)}


def get_form_responses(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    NOTA IMPORTANTE: Obtener respuestas de Microsoft Forms directamente vía API Graph
    NO está soportado actualmente de forma general para el flujo On-Behalf-Of.

    La forma recomendada es usar Power Automate:
    1. Crear un flujo que se dispare con "Cuando se envía una respuesta nueva" (Microsoft Forms trigger).
    2. Usar la acción "Obtener los detalles de la respuesta" (Microsoft Forms action).
    3. Enviar los detalles de la respuesta obtenidos a esta Azure Function (EliteDynamicsPro) mediante
       una acción "HTTP" en Power Automate. Esta acción HTTP haría un POST a tu endpoint 
       (ej. /api/dynamics/action) con una acción específica (ej. "procesar_respuesta_form_powerautomate")
       y el cuerpo JSON de la respuesta del formulario.

    Esta función se deja como placeholder para indicar esta limitación y guiar hacia la solución recomendada.
    El 'client' y 'params' se incluyen por consistencia con otras funciones de acción.

    Args:
        client (AuthenticatedHttpClient): Cliente autenticado (no utilizado directamente aquí).
        params (Dict[str, Any]): Diccionario de parámetros.
            'form_id' (str, opcional): ID del formulario (informativo, no usado por API Graph aquí).

    Returns:
        Dict[str, Any]: Un mensaje indicando que la acción no está soportada directamente.
    """
    form_id_param: Optional[str] = params.get("form_id")
    log_message = (
        f"Intento de obtener respuestas para Form ID '{form_id_param if form_id_param else 'desconocido'}'. "
        "Esta acción NO está soportada directamente por API Graph para el flujo OBO. "
        "Se recomienda usar Power Automate para capturar respuestas y enviarlas a una acción "
        "dedicada en esta Azure Function (ej. 'procesar_respuesta_form_powerautomate')."
    )
    logger.warning(log_message)
    return {
        "status": "not_supported",
        "message": "La obtención de respuestas de Microsoft Forms no está soportada directamente por API Graph en este flujo.",
        "details": (
            "Para obtener respuestas de Forms, configure un flujo en Power Automate que: "
            "1. Se active cuando se envíe una nueva respuesta al formulario deseado. "
            "2. Use la acción 'Obtener los detalles de la respuesta'. "
            "3. Envíe estos detalles (como JSON) mediante una acción HTTP POST a esta Azure Function, "
            "invocando una acción personalizada diseñada para procesar dichos datos (ej. 'procesar_respuesta_form_powerautomate')."
        ),
        "http_status": 501 # Not Implemented (o un código de error personalizado)
    }

# --- FIN DEL MÓDULO actions/forms_actions.py ---