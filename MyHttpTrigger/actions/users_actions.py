# MyHttpTrigger/actions/users_actions.py
import logging
import requests # Para requests.exceptions.HTTPError
from typing import Dict, List, Optional, Any, Union

# Importar el cliente autenticado y las constantes
from ..shared.helpers.http_client import AuthenticatedHttpClient
from ..shared import constants

logger = logging.getLogger(__name__)

# ============================================
# ==== FUNCIONES DE ACCIÓN PARA USUARIOS (Directory) ====
# ============================================

def list_users(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista usuarios en el directorio."""
    url = f"{constants.GRAPH_API_BASE_URL}/users"
    
    api_query_params: Dict[str, Any] = {}
    if params.get('select'): api_query_params['$select'] = params['select']
    else: api_query_params['$select'] = "id,displayName,userPrincipalName,mail,jobTitle,officeLocation,accountEnabled"
    if params.get('filter'): api_query_params['$filter'] = params['filter']
    if params.get('search'): api_query_params['$search'] = params['search'] # Requiere ConsistencyLevel: eventual y Count
    if params.get('orderby'): api_query_params['$orderby'] = params['orderby']
    
    top_per_page: int = min(int(params.get('top_per_page', 25)), constants.MAX_GRAPH_TOP_VALUE_PAGING)
    max_items_total: int = int(params.get('max_items_total', 100))
    api_query_params['$top'] = top_per_page
    if params.get('search'): # $count es requerido con $search
        api_query_params['$count'] = "true"

    all_items: List[Dict[str, Any]] = []
    current_url: Optional[str] = url
    page_count = 0
    
    # Cabeceras adicionales si se usa $search
    custom_headers = {}
    if params.get('search'):
        custom_headers['ConsistencyLevel'] = 'eventual'

    logger.info(f"Listando usuarios (Max total: {max_items_total}, Por pág: {top_per_page}) con params: {api_query_params}")
    try:
        while current_url and len(all_items) < max_items_total:
            page_count += 1
            current_call_params = api_query_params if page_count == 1 else None # Solo para la primera llamada si la URL base no cambia
            
            response = client.get(current_url, scope=constants.GRAPH_SCOPE, params=current_call_params, headers=custom_headers if page_count == 1 else None)
            response_data = response.json()
            
            page_items = response_data.get('value', [])
            if not isinstance(page_items, list): break
            
            for item in page_items:
                if len(all_items) < max_items_total: all_items.append(item)
                else: break
            
            current_url = response_data.get('@odata.nextLink')
            if not current_url or len(all_items) >= max_items_total: break
                
        logger.info(f"Total usuarios recuperados: {len(all_items)} ({page_count} pág procesadas).")
        return {"status": "success", "data": all_items, "total_retrieved": len(all_items), "pages_processed": page_count}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP listando usuarios: {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error listando usuarios: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al listar usuarios: {type(e).__name__}", "details": str(e)}

def get_user(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Obtiene un usuario específico por ID o UserPrincipalName."""
    user_id_or_upn: Optional[str] = params.get("user_id") or params.get("user_principal_name")
    if not user_id_or_upn:
        return {"status": "error", "message": "Se requiere 'user_id' o 'user_principal_name'.", "http_status": 400}

    url = f"{constants.GRAPH_API_BASE_URL}/users/{user_id_or_upn}"
    api_query_params: Dict[str, Any] = {}
    if params.get('select'): 
        api_query_params['$select'] = params['select']
    else: # Default select
        api_query_params['$select'] = "id,displayName,userPrincipalName,mail,jobTitle,officeLocation,accountEnabled,businessPhones,mobilePhone,department,employeeId,givenName,surname"


    logger.info(f"Obteniendo usuario '{user_id_or_upn}'")
    try:
        response = client.get(url, scope=constants.GRAPH_SCOPE, params=api_query_params if api_query_params else None)
        user_data = response.json()
        return {"status": "success", "data": user_data}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP obteniendo usuario '{user_id_or_upn}': {status_code_resp} - {error_details[:300]}", exc_info=False)
        if status_code_resp == 404:
            return {"status": "error", "message": f"Usuario '{user_id_or_upn}' no encontrado.", "http_status": 404, "details": error_details}
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error obteniendo usuario '{user_id_or_upn}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al obtener usuario: {type(e).__name__}", "details": str(e)}

def create_user(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Crea un nuevo usuario."""
    user_payload: Optional[Dict[str, Any]] = params.get("user_payload")
    if not user_payload or not isinstance(user_payload, dict):
        return {"status": "error", "message": "Parámetro 'user_payload' (dict) es requerido.", "http_status": 400}

    # Validar campos mínimos requeridos para crear un usuario
    required_fields = ["accountEnabled", "displayName", "mailNickname", "userPrincipalName", "passwordProfile"]
    if not all(field in user_payload for field in required_fields):
        missing = [field for field in required_fields if field not in user_payload]
        return {"status": "error", "message": f"Faltan campos requeridos en 'user_payload': {', '.join(missing)}.", "http_status": 400}
    if not isinstance(user_payload["passwordProfile"], dict) or "password" not in user_payload["passwordProfile"]:
        return {"status": "error", "message": "'passwordProfile' debe ser un dict y contener 'password'.", "http_status": 400}


    url = f"{constants.GRAPH_API_BASE_URL}/users"
    logger.info(f"Creando nuevo usuario con UPN: {user_payload.get('userPrincipalName', 'N/A')}")
    try:
        response = client.post(url, scope=constants.GRAPH_SCOPE, json_data=user_payload)
        created_user_data = response.json()
        # La API devuelve el objeto de usuario creado, pero sin la contraseña.
        return {"status": "success", "data": created_user_data, "message": "Usuario creado exitosamente."}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP creando usuario: {status_code_resp} - {error_details[:500]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error creando usuario: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al crear usuario: {type(e).__name__}", "details": str(e)}

def update_user(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Actualiza un usuario existente."""
    user_id_or_upn: Optional[str] = params.get("user_id") or params.get("user_principal_name")
    update_payload: Optional[Dict[str, Any]] = params.get("update_payload")
    if not user_id_or_upn:
        return {"status": "error", "message": "Se requiere 'user_id' o 'user_principal_name'.", "http_status": 400}
    if not update_payload or not isinstance(update_payload, dict) or not update_payload: # Payload no debe ser vacío
        return {"status": "error", "message": "Parámetro 'update_payload' (dict no vacío) es requerido.", "http_status": 400}

    url = f"{constants.GRAPH_API_BASE_URL}/users/{user_id_or_upn}"
    logger.info(f"Actualizando usuario '{user_id_or_upn}' con payload: {update_payload}")
    try:
        # PATCH no devuelve contenido por defecto (204 No Content)
        response = client.patch(url, scope=constants.GRAPH_SCOPE, json_data=update_payload)
        if response.status_code == 204:
            logger.info(f"Usuario '{user_id_or_upn}' actualizado exitosamente (204 No Content).")
            # Se podría hacer un GET para devolver el usuario actualizado si es necesario
            get_user_params = {"user_id": user_id_or_upn}
            if params.get("select_after_update"): get_user_params["select"] = params["select_after_update"]
            updated_user_info = get_user(client, get_user_params) # Llama a la función get_user de este módulo
            if updated_user_info["status"] == "success":
                return {"status": "success", "message": "Usuario actualizado.", "data": updated_user_info["data"]}
            return {"status": "success", "message": "Usuario actualizado (204), pero falló la re-obtención.", "data": {"id": user_id_or_upn}}
        else: # Casos raros donde PATCH podría devolver 200 OK con contenido
            logger.warning(f"Usuario '{user_id_or_upn}' actualizado con status {response.status_code}. Respuesta: {response.text[:200]}")
            return {"status": "success", "message": f"Usuario actualizado con status {response.status_code}.", "data": response.json() if response.content else None, "http_status": response.status_code}

    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP actualizando usuario '{user_id_or_upn}': {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error actualizando usuario '{user_id_or_upn}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al actualizar usuario: {type(e).__name__}", "details": str(e)}

def delete_user(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Elimina un usuario (soft delete por defecto)."""
    user_id_or_upn: Optional[str] = params.get("user_id") or params.get("user_principal_name")
    if not user_id_or_upn:
        return {"status": "error", "message": "Se requiere 'user_id' o 'user_principal_name'.", "http_status": 400}

    url = f"{constants.GRAPH_API_BASE_URL}/users/{user_id_or_upn}"
    logger.info(f"Eliminando usuario '{user_id_or_upn}'")
    try:
        response = client.delete(url, scope=constants.GRAPH_SCOPE)
        if response.status_code == 204:
            return {"status": "success", "message": f"Usuario '{user_id_or_upn}' eliminado exitosamente."}
        else:
            error_details = response.text[:200] if hasattr(response, 'text') else "Respuesta inesperada."
            logger.error(f"Respuesta inesperada {response.status_code} al eliminar usuario '{user_id_or_upn}': {error_details}")
            return {"status": "error", "message": f"Respuesta inesperada {response.status_code} al eliminar usuario.", "details": error_details, "http_status": response.status_code}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP eliminando usuario '{user_id_or_upn}': {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error eliminando usuario '{user_id_or_upn}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al eliminar usuario: {type(e).__name__}", "details": str(e)}


# ============================================
# ==== FUNCIONES DE ACCIÓN PARA GRUPOS (Directory) ====
# ============================================

def list_groups(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista grupos en el directorio."""
    url = f"{constants.GRAPH_API_BASE_URL}/groups"
    api_query_params: Dict[str, Any] = {}
    if params.get('select'): api_query_params['$select'] = params['select']
    else: api_query_params['$select'] = "id,displayName,description,mailEnabled,securityEnabled,groupTypes,visibility"
    if params.get('filter'): api_query_params['$filter'] = params['filter'] # Ej: "startswith(displayName,'Test')"
    if params.get('search'): api_query_params['$search'] = params['search'] # Requiere ConsistencyLevel: eventual y Count
    if params.get('orderby'): api_query_params['$orderby'] = params['orderby']

    top_per_page: int = min(int(params.get('top_per_page', 25)), constants.MAX_GRAPH_TOP_VALUE_PAGING)
    max_items_total: int = int(params.get('max_items_total', 100))
    api_query_params['$top'] = top_per_page
    if params.get('search'): api_query_params['$count'] = "true"

    all_items: List[Dict[str, Any]] = []
    current_url: Optional[str] = url
    page_count = 0
    
    custom_headers = {}
    if params.get('search'):
        custom_headers['ConsistencyLevel'] = 'eventual'

    logger.info(f"Listando grupos (Max total: {max_items_total}, Por pág: {top_per_page}) con params: {api_query_params}")
    try:
        while current_url and len(all_items) < max_items_total:
            page_count += 1
            current_call_params = api_query_params if page_count == 1 else None
            
            response = client.get(current_url, scope=constants.GRAPH_SCOPE, params=current_call_params, headers=custom_headers if page_count == 1 else None)
            response_data = response.json()
            
            page_items = response_data.get('value', [])
            if not isinstance(page_items, list): break
            
            for item in page_items:
                if len(all_items) < max_items_total: all_items.append(item)
                else: break
            
            current_url = response_data.get('@odata.nextLink')
            if not current_url or len(all_items) >= max_items_total: break
                
        logger.info(f"Total grupos recuperados: {len(all_items)} ({page_count} pág procesadas).")
        return {"status": "success", "data": all_items, "total_retrieved": len(all_items), "pages_processed": page_count}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP listando grupos: {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error listando grupos: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al listar grupos: {type(e).__name__}", "details": str(e)}

def get_group(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Obtiene un grupo específico por ID."""
    group_id: Optional[str] = params.get("group_id")
    if not group_id:
        return {"status": "error", "message": "Se requiere 'group_id'.", "http_status": 400}

    url = f"{constants.GRAPH_API_BASE_URL}/groups/{group_id}"
    api_query_params: Dict[str, Any] = {}
    if params.get('select'): 
        api_query_params['$select'] = params['select']
    else: # Default select
        api_query_params['$select'] = "id,displayName,description,mailEnabled,securityEnabled,groupTypes,visibility,createdDateTime"

    logger.info(f"Obteniendo grupo '{group_id}'")
    try:
        response = client.get(url, scope=constants.GRAPH_SCOPE, params=api_query_params if api_query_params else None)
        group_data = response.json()
        return {"status": "success", "data": group_data}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP obteniendo grupo '{group_id}': {status_code_resp} - {error_details[:300]}", exc_info=False)
        if status_code_resp == 404:
            return {"status": "error", "message": f"Grupo '{group_id}' no encontrado.", "http_status": 404, "details": error_details}
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error obteniendo grupo '{group_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al obtener grupo: {type(e).__name__}", "details": str(e)}

def list_group_members(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista los miembros (usuarios, grupos, etc.) de un grupo específico."""
    group_id: Optional[str] = params.get("group_id")
    if not group_id:
        return {"status": "error", "message": "Se requiere 'group_id'.", "http_status": 400}

    # /members puede devolver diferentes tipos de DirectoryObject.
    # Para obtener solo usuarios: /groups/{id}/members/microsoft.graph.user
    # Para obtener solo grupos: /groups/{id}/members/microsoft.graph.group
    # Por defecto, lista todos los tipos de miembros.
    member_type_filter: Optional[str] = params.get("member_type") # "user", "group", "device", etc.
    url_segment = "/members"
    if member_type_filter:
        if member_type_filter.lower() == "user": url_segment = "/members/microsoft.graph.user"
        elif member_type_filter.lower() == "group": url_segment = "/members/microsoft.graph.group"
        # Añadir más tipos si es necesario
        else: logger.info(f"Tipo de miembro '{member_type_filter}' no reconocido para filtro de URL, listando todos los tipos.")

    url = f"{constants.GRAPH_API_BASE_URL}/groups/{group_id}{url_segment}"
    
    api_query_params: Dict[str, Any] = {}
    if params.get('select'): api_query_params['$select'] = params['select']
    else: api_query_params['$select'] = "id,displayName,userPrincipalName,mail" # Select común para usuarios
    # $filter, $search, $orderby también son aplicables aquí.
    if params.get('filter'): api_query_params['$filter'] = params['filter']

    top_per_page: int = min(int(params.get('top_per_page', 25)), constants.MAX_GRAPH_TOP_VALUE_PAGING_USERS) # Puede ser hasta 999 para miembros
    max_items_total: int = int(params.get('max_items_total', 100))
    api_query_params['$top'] = top_per_page
    
    all_items: List[Dict[str, Any]] = []
    current_url: Optional[str] = url
    page_count = 0

    logger.info(f"Listando miembros del grupo '{group_id}' (Tipo: {member_type_filter or 'todos'}, Max total: {max_items_total})")
    try:
        while current_url and len(all_items) < max_items_total:
            page_count += 1
            current_call_params = api_query_params if page_count == 1 else None
            
            response = client.get(current_url, scope=constants.GRAPH_SCOPE, params=current_call_params)
            response_data = response.json()
            
            page_items = response_data.get('value', [])
            if not isinstance(page_items, list): break
            
            for item in page_items:
                if len(all_items) < max_items_total: all_items.append(item)
                else: break
            
            current_url = response_data.get('@odata.nextLink')
            if not current_url or len(all_items) >= max_items_total: break
                
        logger.info(f"Total miembros recuperados para grupo '{group_id}': {len(all_items)} ({page_count} pág procesadas).")
        return {"status": "success", "data": all_items, "total_retrieved": len(all_items), "pages_processed": page_count}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP listando miembros del grupo '{group_id}': {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error listando miembros del grupo '{group_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al listar miembros de grupo: {type(e).__name__}", "details": str(e)}

def add_group_member(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Añade un miembro (usuario) a un grupo."""
    group_id: Optional[str] = params.get("group_id")
    member_id: Optional[str] = params.get("member_id") # ID del usuario a añadir
    if not group_id or not member_id:
        return {"status": "error", "message": "Se requieren 'group_id' y 'member_id'.", "http_status": 400}

    url = f"{constants.GRAPH_API_BASE_URL}/groups/{group_id}/members/$ref"
    # El payload es una referencia al objeto de directorio a añadir
    payload = {
        "@odata.id": f"{constants.GRAPH_API_BASE_URL}/directoryObjects/{member_id}"
        # O más específicamente si se sabe que es un usuario:
        # "@odata.id": f"{constants.GRAPH_API_BASE_URL}/users/{member_id}"
    }
    
    logger.info(f"Añadiendo miembro '{member_id}' al grupo '{group_id}'")
    try:
        # Añadir un miembro es un POST y devuelve 204 No Content si tiene éxito.
        response = client.post(url, scope=constants.GRAPH_SCOPE, json_data=payload)
        if response.status_code == 204:
            return {"status": "success", "message": f"Miembro '{member_id}' añadido al grupo '{group_id}'."}
        else:
            # Esto no debería ocurrir si no hay excepción HTTPError
            error_details = response.text[:200] if hasattr(response, 'text') else "Respuesta inesperada."
            logger.error(f"Respuesta inesperada {response.status_code} al añadir miembro al grupo: {error_details}")
            return {"status": "error", "message": f"Respuesta inesperada {response.status_code}.", "details": error_details, "http_status": response.status_code}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP añadiendo miembro '{member_id}' al grupo '{group_id}': {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error añadiendo miembro al grupo: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al añadir miembro: {type(e).__name__}", "details": str(e)}

def remove_group_member(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Elimina un miembro (usuario) de un grupo."""
    group_id: Optional[str] = params.get("group_id")
    member_id: Optional[str] = params.get("member_id") # ID del usuario a eliminar
    if not group_id or not member_id:
        return {"status": "error", "message": "Se requieren 'group_id' y 'member_id'.", "http_status": 400}

    # El endpoint para eliminar es /groups/{group_id}/members/{member_id}/$ref
    url = f"{constants.GRAPH_API_BASE_URL}/groups/{group_id}/members/{member_id}/$ref"
    
    logger.info(f"Eliminando miembro '{member_id}' del grupo '{group_id}'")
    try:
        # Eliminar un miembro es un DELETE y devuelve 204 No Content si tiene éxito.
        response = client.delete(url, scope=constants.GRAPH_SCOPE)
        if response.status_code == 204:
            return {"status": "success", "message": f"Miembro '{member_id}' eliminado del grupo '{group_id}'."}
        else:
            error_details = response.text[:200] if hasattr(response, 'text') else "Respuesta inesperada."
            logger.error(f"Respuesta inesperada {response.status_code} al eliminar miembro del grupo: {error_details}")
            return {"status": "error", "message": f"Respuesta inesperada {response.status_code}.", "details": error_details, "http_status": response.status_code}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP eliminando miembro '{member_id}' del grupo '{group_id}': {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error eliminando miembro del grupo: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al eliminar miembro: {type(e).__name__}", "details": str(e)}

def check_group_membership(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Verifica si un usuario es miembro de un grupo."""
    user_id: Optional[str] = params.get("user_id") # ID del usuario
    group_ids: Optional[Union[str, List[str]]] = params.get("group_ids") # ID o lista de IDs de grupos
    
    if not user_id or not group_ids:
        return {"status": "error", "message": "Se requieren 'user_id' y 'group_ids' (string o lista).", "http_status": 400}

    # El endpoint es /users/{user_id}/checkMemberGroups
    url = f"{constants.GRAPH_API_BASE_URL}/users/{user_id}/checkMemberGroups"
    
    payload: Dict[str, List[str]]
    if isinstance(group_ids, str):
        payload = {"groupIds": [group_ids]}
    elif isinstance(group_ids, list):
        payload = {"groupIds": group_ids}
    else:
        return {"status": "error", "message": "'group_ids' debe ser un string o una lista de strings.", "http_status": 400}

    logger.info(f"Verificando pertenencia del usuario '{user_id}' a los grupos: {payload['groupIds']}")
    try:
        response = client.post(url, scope=constants.GRAPH_SCOPE, json_data=payload)
        # Devuelve una lista de IDs de los grupos a los que el usuario pertenece.
        member_of_group_ids = response.json().get("value", [])
        
        # Construir un resultado más legible
        results: Dict[str, bool] = {gid: (gid in member_of_group_ids) for gid in payload["groupIds"]}
        
        return {"status": "success", "data": results, "message": "Verificación de membresía completada."}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP verificando membresía de grupo para usuario '{user_id}': {status_code_resp} - {error_details[:300]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error verificando membresía de grupo: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al verificar membresía: {type(e).__name__}", "details": str(e)}

# Nota: Crear y eliminar grupos (/groups POST y DELETE /groups/{id}) no estaban en la lista del script,
# pero podrían añadirse si son necesarios. Se seguiría un patrón similar a create_user/delete_user.

# --- FIN DEL MÓDULO actions/users_actions.py ---