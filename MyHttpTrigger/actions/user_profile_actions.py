# MyHttpTrigger/actions/user_profile_actions.py
import logging
import requests # Solo para tipos de excepción
import json
from typing import Dict, Optional, Any, Union

# Importar helper y constantes
try:
    from ..shared.helpers.http_client import hacer_llamada_api
    from ..shared.constants import BASE_URL, GRAPH_API_DEFAULT_TIMEOUT, APP_NAME
except ImportError as e:
    logging.critical(f"Error CRÍTICO importando dependencias compartidas en UserProfile: {e}.", exc_info=True)
    BASE_URL = "https://graph.microsoft.com/v1.0"
    GRAPH_API_DEFAULT_TIMEOUT = 45
    APP_NAME = "EliteDynamicsPro" # Fallback
    raise ImportError(f"No se pudo importar 'hacer_llamada_api' o constantes: {e}") from e

logger = logging.getLogger(f"{APP_NAME}.actions.user_profile")

# ---- FUNCIONES DE ACCIÓN PARA PERFIL DE USUARIO (/me) ----
# Requieren permisos delegados como User.Read, User.ReadBasic.All, Directory.Read.All, etc.

def get_my_profile(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Obtiene información del perfil del usuario autenticado (/me).

    Args:
        parametros (Dict[str, Any]):
            'select' (str, opcional): Campos a seleccionar, separados por coma.
                                      Ej: "id,displayName,mail,userPrincipalName,jobTitle".
        headers (Dict[str, str]): Cabeceras con token OBO.

    Returns:
        Dict[str, Any]: {"status": "success", "data": {perfil}} o error.
    """
    select_fields: Optional[str] = parametros.get('select')
    
    url = f"{BASE_URL}/me"
    query_params = {'$select': select_fields} if select_fields else None
    
    logger.info(f"Obteniendo perfil de /me (Select: {select_fields or 'default'})")
    try:
        profile_data = hacer_llamada_api("GET", url, headers, params=query_params, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": profile_data}
    except Exception as e:
        logger.error(f"Error obteniendo perfil de /me: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al obtener perfil: {type(e).__name__}", "http_status": status_code, "details": details}

def get_my_manager(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Obtiene información sobre el manager directo del usuario autenticado.
    Requiere permisos como User.Read.All o Directory.Read.All.

    Args:
        parametros (Dict[str, Any]):
             'select' (str, opcional): Campos del manager a seleccionar. Ej: "id,displayName,mail".
        headers (Dict[str, str]): Cabeceras con token OBO.

    Returns:
        Dict[str, Any]: {"status": "success", "data": {manager_profile}} o error.
    """
    select_fields: Optional[str] = parametros.get('select')
    
    url = f"{BASE_URL}/me/manager"
    query_params = {'$select': select_fields} if select_fields else None
    
    logger.info(f"Obteniendo manager de /me (Select: {select_fields or 'default'})")
    try:
        manager_data = hacer_llamada_api("GET", url, headers, params=query_params, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        if manager_data: # Manager puede no existir (sería 200 OK con cuerpo vacío o error 404?) Graph usualmente 404 si no hay manager.
             return {"status": "success", "data": manager_data}
        else:
             # Si hacer_llamada_api devuelve None (ej. por 204), indicamos que no hay manager.
             logger.info("No se encontró manager para el usuario (o respuesta vacía).")
             return {"status": "success", "data": None, "message": "No se encontró manager para este usuario."}
    except Exception as e:
        logger.error(f"Error obteniendo manager de /me: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        # Específicamente manejar 404 como "No encontrado"
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            if status_code == 404:
                 return {"status": "success", "data": None, "message": "No se encontró manager para este usuario."}
        return {"status": "error", "message": f"Error al obtener manager: {type(e).__name__}", "http_status": status_code, "details": details}

def list_my_direct_reports(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Lista los reportes directos del usuario autenticado.
    Requiere permisos como User.Read.All o Directory.Read.All.
    Maneja paginación simple.

    Args:
        parametros (Dict[str, Any]):
             'select' (str, opcional): Campos de los reportes a seleccionar. Ej: "id,displayName,mail".
             'top' (int, opcional): Máximo a devolver. Default 25.
    headers (Dict[str, str]): Cabeceras con token OBO.

    Returns:
        Dict[str, Any]: {"status": "success", "data": [lista_reportes]} o error.
    """
    select_fields: Optional[str] = parametros.get('select')
    top: int = min(int(parametros.get('top', 25)), 999)

    url_base = f"{BASE_URL}/me/directReports"
    query_params: Dict[str, Any] = {'$top': top}
    if select_fields: query_params['$select'] = select_fields
    
    all_reports: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0; max_pages = 5 # Limitar paginación para evitar cargas excesivas
    
    logger.info(f"Listando reportes directos de /me (Select: {select_fields or 'default'}, Max: {top})")

    try:
        while current_url and page_count < max_pages:
            page_count += 1
            params_for_call = query_params if current_url == url_base and page_count == 1 else None
            logger.debug(f" Obteniendo página {page_count} de reportes directos desde: {current_url}")
            response_data = hacer_llamada_api("GET", current_url, headers, params=params_for_call, timeout=GRAPH_API_DEFAULT_TIMEOUT)

            if response_data and isinstance(response_data, dict) and 'value' in response_data:
                items_in_page = response_data.get('value', [])
                if not isinstance(items_in_page, list): break
                all_reports.extend(items_in_page)
                current_url = response_data.get('@odata.nextLink')
                if not current_url or len(all_reports) >= top: # Parar si ya tenemos suficientes o no hay más
                    break
            else: break
        if page_count >= max_pages: logger.warning(f"Límite de {max_pages} páginas alcanzado listando reportes directos.")

        logger.info(f"Total reportes directos recuperados: {len(all_reports)}")
        return {"status": "success", "data": all_reports[:top], "total_retrieved": len(all_reports), "pages_processed": page_count}
    except Exception as e:
        logger.error(f"Error listando reportes directos: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al listar reportes directos: {type(e).__name__}", "http_status": status_code, "details": details}

def get_my_photo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Union[bytes, Dict[str, Any]]:
    """
    Obtiene la foto de perfil del usuario autenticado (si existe).
    Requiere User.ReadBasic.All o User.Read.All.
    Devuelve bytes si tiene éxito, o dict de error.

    Args:
        parametros (Dict[str, Any]):
             'size' (str, opcional): Tamaño de la foto (ej. '48x48', '64x64', ..., '648x648'). Default el más grande disponible.
        headers (Dict[str, str]): Cabeceras con token OBO.

    Returns:
        Union[bytes, Dict[str, Any]]: Contenido binario de la foto o diccionario de error.
    """
    size: Optional[str] = parametros.get('size')
    
    endpoint = "/me/photo/$value" if not size else f"/me/photos/{size}/$value"
    url = f"{BASE_URL}{endpoint}"
    
    logger.info(f"Obteniendo foto de perfil de /me (Tamaño: {size or 'default'})")
    
    # Añadir Accept header adecuado podría ser útil, pero /content y /$value usualmente funcionan sin él.
    # request_headers = headers.copy()
    # request_headers['Accept'] = 'image/jpeg' # O el tipo que esperes

    try:
        photo_bytes = hacer_llamada_api("GET", url, headers, timeout=GRAPH_API_DEFAULT_TIMEOUT, expect_json=False, stream=True)
        
        if isinstance(photo_bytes, bytes):
            logger.info(f"Foto de perfil obtenida ({len(photo_bytes)} bytes).")
            return photo_bytes # Devuelve bytes directamente
        elif photo_bytes is None: # Podría ser un 204 si no hay foto? Graph usualmente 404.
             logger.info("No se encontró foto de perfil para el usuario (respuesta vacía).")
             return {"status": "success", "data": None, "message": "El usuario no tiene foto de perfil configurada."}
        else:
            logger.error(f"Respuesta inesperada del helper al obtener foto: {type(photo_bytes)}")
            return {"status": "error", "message": "Error interno al obtener foto (respuesta inesperada del helper)."}
            
    except Exception as e:
        logger.error(f"Error obteniendo foto de perfil: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        # Manejar 404 específicamente como "foto no encontrada"
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            if status_code == 404:
                 return {"status": "success", "data": None, "message": "El usuario no tiene foto de perfil configurada o el tamaño solicitado no existe.", "details": details}
        return {"status": "error", "message": f"Error al obtener foto de perfil: {type(e).__name__}", "http_status": status_code, "details": details}

# --- FIN DEL MÓDULO actions/user_profile_actions.py ---