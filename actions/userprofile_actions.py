# -*- coding: utf-8 -*-
# MyHttpTrigger/actions/userprofile_actions.py
import logging
from typing import Dict, List, Optional, Any, Union # Añadir más tipos según necesidad

# Importar el cliente autenticado y las constantes
from shared.helpers.http_client import AuthenticatedHttpClient
from shared import constants

logger = logging.getLogger(__name__)

# --- Placeholder Functions ---

def get_my_direct_reports(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Placeholder para la acción: get_my_direct_reports
    Servicio: userprofile
    """
    action_name_log = "get_my_direct_reports" 
    logger.warning(f"Acción '{action_name_log}' del servicio '{__name__}' no implementada todavía.")
    return {
        "status": "not_implemented",
        "message": f"Acción '{action_name_log}' no implementada todavía.",
        "service_module": __name__,
        "http_status": 501
    }

def get_my_manager(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Placeholder para la acción: get_my_manager
    Servicio: userprofile
    """
    action_name_log = "get_my_manager" 
    logger.warning(f"Acción '{action_name_log}' del servicio '{__name__}' no implementada todavía.")
    return {
        "status": "not_implemented",
        "message": f"Acción '{action_name_log}' no implementada todavía.",
        "service_module": __name__,
        "http_status": 501
    }

def get_my_photo(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Placeholder para la acción: get_my_photo
    Servicio: userprofile
    """
    action_name_log = "get_my_photo" 
    logger.warning(f"Acción '{action_name_log}' del servicio '{__name__}' no implementada todavía.")
    return {
        "status": "not_implemented",
        "message": f"Acción '{action_name_log}' no implementada todavía.",
        "service_module": __name__,
        "http_status": 501
    }

def get_my_profile(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Placeholder para la acción: get_my_profile
    Servicio: userprofile
    """
    action_name_log = "get_my_profile" 
    logger.warning(f"Acción '{action_name_log}' del servicio '{__name__}' no implementada todavía.")
    return {
        "status": "not_implemented",
        "message": f"Acción '{action_name_log}' no implementada todavía.",
        "service_module": __name__,
        "http_status": 501
    }

def update_my_profile(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Placeholder para la acción: update_my_profile
    Servicio: userprofile
    """
    action_name_log = "update_my_profile" 
    logger.warning(f"Acción '{action_name_log}' del servicio '{__name__}' no implementada todavía.")
    return {
        "status": "not_implemented",
        "message": f"Acción '{action_name_log}' no implementada todavía.",
        "service_module": __name__,
        "http_status": 501
    }
# MyHttpTrigger/actions/user_profile_actions.py
import logging
import requests # Solo para tipos de excepción
import json
from typing import Dict, Optional, Any, Union, List

# Importar el cliente autenticado y las constantes
from shared.helpers.http_client import AuthenticatedHttpClient
from shared import constants # GRAPH_API_BASE_URL, GRAPH_SCOPE, DEFAULT_API_TIMEOUT

logger = logging.getLogger(__name__)

# ---- FUNCIONES DE ACCIÓN PARA PERFIL DE USUARIO (/me) (Refactorizadas) ----
# Nombres de función ajustados para coincidir con mapping_actions.py (profile_get_my_profile, etc.)

def profile_get_my_profile(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Obtiene información del perfil del usuario autenticado (/me).
    """
    select_fields: Optional[str] = params.get('select')
    
    url = f"{constants.GRAPH_API_BASE_URL}/me"
    query_api_params = {'$select': select_fields} if select_fields else None
    
    logger.info(f"Obteniendo perfil de /me (Select: {select_fields or 'default'})")
    try:
        response = client.get(url, scope=constants.GRAPH_SCOPE, params=query_api_params)
        profile_data = response.json()
        return {"status": "success", "data": profile_data}
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"Error HTTP obteniendo perfil de /me: {http_err.response.status_code} - {http_err.response.text[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {http_err.response.status_code}", "details": http_err.response.text, "http_status": http_err.response.status_code}
    except Exception as e:
        logger.error(f"Error obteniendo perfil de /me: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al obtener perfil: {type(e).__name__}", "details": str(e)}

def profile_get_my_manager(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Obtiene información sobre el manager directo del usuario autenticado.
    """
    select_fields: Optional[str] = params.get('select')
    
    url = f"{constants.GRAPH_API_BASE_URL}/me/manager"
    query_api_params = {'$select': select_fields} if select_fields else None
    
    logger.info(f"Obteniendo manager de /me (Select: {select_fields or 'default'})")
    try:
        response = client.get(url, scope=constants.GRAPH_SCOPE, params=query_api_params)
        # Graph API devuelve 200 OK con los datos del manager si existe.
        # Si no hay manager, devuelve 404 Not Found.
        manager_data = response.json() 
        return {"status": "success", "data": manager_data}
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"Error HTTP obteniendo manager de /me: {http_err.response.status_code} - {http_err.response.text[:200]}", exc_info=False)
        if http_err.response.status_code == 404:
            logger.info("No se encontró manager para el usuario.")
            return {"status": "success", "data": None, "message": "No se encontró manager para este usuario.", "http_status": 404}
        return {"status": "error", "message": f"Error HTTP: {http_err.response.status_code}", "details": http_err.response.text, "http_status": http_err.response.status_code}
    except Exception as e:
        logger.error(f"Error obteniendo manager de /me: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al obtener manager: {type(e).__name__}", "details": str(e)}

def profile_get_my_direct_reports(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Renombrado de list_my_direct_reports
    """
    Lista los reportes directos del usuario autenticado. Maneja paginación simple.
    """
    select_fields: Optional[str] = params.get('select')
    top: int = min(int(params.get('top', 25)), 999) # Graph API $top limit

    url_base = f"{constants.GRAPH_API_BASE_URL}/me/directReports"
    query_api_params: Dict[str, Any] = {'$top': top}
    if select_fields: query_api_params['$select'] = select_fields
    
    all_reports: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0
    # Limitar la paginación interna para esta función, ya que max_items_total no estaba en el original
    # El usuario puede controlar el total con 'top' hasta el límite de Graph.
    max_internal_pages = 5 
    
    logger.info(f"Listando reportes directos de /me (Select: {select_fields or 'default'}, Top: {top})")

    try:
        while current_url and page_count < max_internal_pages:
            page_count += 1
            current_query_params_for_call = query_api_params if current_url == url_base and page_count == 1 else None
            logger.debug(f" Obteniendo página {page_count} de reportes directos desde: {current_url}")
            
            response = client.get(
                url=current_url,
                scope=constants.GRAPH_SCOPE,
                params=current_query_params_for_call
            )
            response_data = response.json()

            if 'value' in response_data:
                items_in_page = response_data.get('value', [])
                if not isinstance(items_in_page, list): break
                all_reports.extend(items_in_page)
                
                current_url = response_data.get('@odata.nextLink')
                # Parar si ya tenemos suficientes (aunque $top debería manejar esto en la API) o no hay más
                if not current_url or len(all_reports) >= top: 
                    break
            else: break
        if page_count >= max_internal_pages and current_url: 
            logger.warning(f"Límite interno de {max_internal_pages} páginas alcanzado listando reportes directos. Puede haber más resultados.")

        logger.info(f"Total reportes directos recuperados: {len(all_reports)}")
        # Devolver solo hasta 'top' como máximo, aunque la paginación interna haya traído más
        return {"status": "success", "data": all_reports[:top], "total_retrieved": len(all_reports), "pages_processed": page_count}
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"Error HTTP listando reportes directos: {http_err.response.status_code} - {http_err.response.text[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {http_err.response.status_code}", "details": http_err.response.text, "http_status": http_err.response.status_code}
    except Exception as e:
        logger.error(f"Error listando reportes directos: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al listar reportes directos: {type(e).__name__}", "details": str(e)}

def profile_get_my_photo(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Union[bytes, Dict[str, Any]]: # Renombrado de get_my_photo
    """
    Obtiene la foto de perfil del usuario autenticado (si existe).
    Devuelve bytes si tiene éxito, o dict de error.
    """
    size: Optional[str] = params.get('size') # ej. '48x48', '64x64', etc.
    
    endpoint = "/me/photo/$value" if not size else f"/me/photos/{size}/$value"
    url = f"{constants.GRAPH_API_BASE_URL}{endpoint}"
    
    logger.info(f"Obteniendo foto de perfil de /me (Tamaño: {size or 'default'}) desde {url}")
    
    try:
        # Para contenido binario, el client.get ya debería manejarlo bien.
        # stream=True es útil para archivos grandes, para fotos de perfil no es tan crítico pero no daña.
        response = client.get(url, scope=constants.GRAPH_SCOPE, stream=True)
        
        # response.content tendrá los bytes. El client ya hizo raise_for_status.
        photo_bytes = response.content
        
        if photo_bytes: # Si hay contenido
            logger.info(f"Foto de perfil obtenida ({len(photo_bytes)} bytes).")
            return photo_bytes # Devolver bytes directamente
        else:
            # Esto podría ocurrir si el endpoint devuelve 200 OK pero con cuerpo vacío (raro para /$value)
            # O si la respuesta fue un 204 No Content (aún más raro para foto).
            # Graph API usualmente devuelve 404 si la foto no existe.
            logger.info("No se encontró contenido en la respuesta de la foto de perfil.")
            return {"status": "success", "data": None, "message": "No se encontró contenido en la foto de perfil (respuesta vacía)."}
            
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"Error HTTP obteniendo foto de perfil: {http_err.response.status_code} - {http_err.response.text[:200]}", exc_info=False)
        if http_err.response.status_code == 404:
            return {"status": "success", "data": None, "message": "El usuario no tiene foto de perfil configurada o el tamaño solicitado no existe.", "http_status": 404}
        return {"status": "error", "message": f"Error HTTP: {http_err.response.status_code}", "details": http_err.response.text, "http_status": http_err.response.status_code}
    except Exception as e:
        logger.error(f"Error obteniendo foto de perfil: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al obtener foto de perfil: {type(e).__name__}", "details": str(e)}

# Nota: Faltaría profile_update_my_profile del mapping_actions si se quiere implementar.
# def profile_update_my_profile(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
#     # PATCH a /me con los campos permitidos (ej. aboutMe, birthday, etc.)
#     # ...
#     pass