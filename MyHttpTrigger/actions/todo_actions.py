# MyHttpTrigger/actions/todo_actions.py
import logging
import requests # Solo para tipos de excepción
# import json # No se usa directamente si AuthenticatedHttpClient maneja .json()
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone as dt_timezone # Alias para claridad

# Importar el cliente autenticado y las constantes
from ..shared.helpers.http_client import AuthenticatedHttpClient
from ..shared import constants

logger = logging.getLogger(__name__)

# --- Helper para parsear y formatear datetimes a UTC ISO 8601 ---
# (Mantenido aquí ya que es específico para el manejo de fechas en ToDo)
def _parse_and_utc_datetime_str(datetime_str: Any, field_name_for_log: str) -> str:
    if isinstance(datetime_str, datetime):
        dt_obj = datetime_str
    elif isinstance(datetime_str, str):
        try:
            if datetime_str.endswith('Z'):
                dt_obj = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
            elif '+' in datetime_str[10:] or '-' in datetime_str[10:]: # Check for timezone offset
                 dt_obj = datetime.fromisoformat(datetime_str)
            else: # No timezone info, assume naive or needs to be set
                dt_obj = datetime.fromisoformat(datetime_str)
        except ValueError as e:
            logger.error(f"Formato de fecha/hora inválido para '{field_name_for_log}': '{datetime_str}'. Error: {e}")
            raise ValueError(f"Formato de fecha/hora inválido para '{field_name_for_log}': '{datetime_str}'. Se esperaba ISO 8601.") from e
    else:
        raise ValueError(f"Tipo inválido para '{field_name_for_log}': se esperaba string o datetime.")

    if dt_obj.tzinfo is None or dt_obj.tzinfo.utcoffset(dt_obj) is None:
        logger.debug(f"Fecha/hora '{datetime_str}' para '{field_name_for_log}' es naive o tzinfo no tiene offset. Asumiendo y estableciendo a UTC.")
        dt_obj_utc = dt_obj.replace(tzinfo=dt_timezone.utc)
    else:
        dt_obj_utc = dt_obj.astimezone(dt_timezone.utc)
    
    return dt_obj_utc.isoformat(timespec='seconds').replace('+00:00', 'Z')

# =================================
# ==== FUNCIONES ACCIÓN TO-DO  ====
# =================================

# --- Funciones mapeadas en ACTION_MAP (nombres corregidos) ---

def list_task_lists(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista las listas de tareas de ToDo del usuario (/me/todo/lists)."""
    url_base = f"{constants.GRAPH_API_BASE_URL}/me/todo/lists"
    
    # Paginación y filtros
    top_per_page: int = min(int(params.get('top_per_page', 25)), constants.MAX_GRAPH_TOP_VALUE_PAGING)
    max_items_total: int = int(params.get('max_items_total', 100))
    select: Optional[str] = params.get('select')
    filter_query: Optional[str] = params.get('filter_query')
    order_by: Optional[str] = params.get('order_by')

    query_api_params_initial: Dict[str, Any] = {'$top': top_per_page}
    if select: 
        query_api_params_initial['$select'] = select
    else: # Select por defecto
        query_api_params_initial['$select'] = "id,displayName,isOwner,isShared,wellknownListName"
    if filter_query: 
        query_api_params_initial['$filter'] = filter_query
    if order_by: 
        query_api_params_initial['$orderby'] = order_by

    all_lists: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0
    logger.info(f"Listando listas de ToDo para /me (Max total: {max_items_total}, Por pág: {top_per_page})")
    try:
        while current_url and len(all_lists) < max_items_total:
            page_count += 1
            current_call_params = query_api_params_initial if page_count == 1 else None
            logger.debug(f"Obteniendo página {page_count} de listas ToDo desde: {current_url} con params: {current_call_params}")
            
            response = client.get(current_url, scope=constants.GRAPH_SCOPE, params=current_call_params)
            response_data = response.json()
            
            page_items = response_data.get('value', [])
            if not isinstance(page_items, list):
                logger.warning(f"Respuesta inesperada para listas ToDo página {page_count}, 'value' no es una lista.")
                break
            
            for item in page_items:
                if len(all_lists) < max_items_total:
                    all_lists.append(item)
                else:
                    break 
            
            current_url = response_data.get('@odata.nextLink')
            if not current_url or len(all_lists) >= max_items_total:
                break
                
        logger.info(f"Total listas ToDo recuperadas: {len(all_lists)} ({page_count} pág procesadas).")
        return {"status": "success", "data": all_lists, "total_retrieved": len(all_lists), "pages_processed": page_count}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP listando listas ToDo: {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error listando listas ToDo: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al listar listas ToDo: {type(e).__name__}", "details": str(e)}

def create_task_list(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Crea una nueva lista de tareas de ToDo para el usuario."""
    displayName: Optional[str] = params.get("displayName")
    if not displayName: 
        return {"status": "error", "message": "Parámetro 'displayName' (nombre de la lista) es requerido.", "http_status": 400}
    
    url = f"{constants.GRAPH_API_BASE_URL}/me/todo/lists"
    body = {"displayName": displayName}
    logger.info(f"Creando lista de ToDo '{displayName}' para /me")
    try:
        response = client.post(url, scope=constants.GRAPH_SCOPE, json_data=body)
        list_data = response.json()
        return {"status": "success", "data": list_data, "message": "Lista ToDo creada exitosamente."}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP creando lista ToDo '{displayName}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error creando lista ToDo '{displayName}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al crear lista ToDo: {type(e).__name__}", "details": str(e)}

def list_tasks(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista las tareas de una lista de ToDo específica."""
    list_id: Optional[str] = params.get("list_id")
    if not list_id: 
        return {"status": "error", "message": "Parámetro 'list_id' es requerido para listar tareas.", "http_status": 400}

    # Paginación y filtros
    top_per_page: int = min(int(params.get('top_per_page', 25)), constants.MAX_GRAPH_TOP_VALUE_PAGING)
    max_items_total: int = int(params.get('max_items_total', 100))
    select: Optional[str] = params.get('select')
    filter_query: Optional[str] = params.get('filter_query') # Ej: "status ne 'completed'"
    order_by: Optional[str] = params.get('order_by')

    url_base = f"{constants.GRAPH_API_BASE_URL}/me/todo/lists/{list_id}/tasks"
    query_api_params_initial: Dict[str, Any] = {'$top': top_per_page}
    if select: 
        query_api_params_initial['$select'] = select
    else: # Select por defecto
        query_api_params_initial['$select'] = "id,title,status,importance,isReminderOn,createdDateTime,lastModifiedDateTime,dueDateTime,completedDateTime"
    if filter_query: 
        query_api_params_initial['$filter'] = filter_query
    if order_by: 
        query_api_params_initial['$orderby'] = order_by
    
    all_tasks: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0
    logger.info(f"Listando tareas ToDo de lista '{list_id}' (Max total: {max_items_total}, Por pág: {top_per_page})")
    try:
        while current_url and len(all_tasks) < max_items_total:
            page_count += 1
            current_call_params = query_api_params_initial if page_count == 1 else None
            
            response = client.get(current_url, scope=constants.GRAPH_SCOPE, params=current_call_params)
            response_data = response.json()
            
            page_items = response_data.get('value', [])
            if not isinstance(page_items, list):
                logger.warning(f"Respuesta inesperada para tareas ToDo página {page_count}, 'value' no es una lista.")
                break

            for item in page_items:
                if len(all_tasks) < max_items_total:
                    all_tasks.append(item)
                else:
                    break
            
            current_url = response_data.get('@odata.nextLink')
            if not current_url or len(all_tasks) >= max_items_total:
                break
                
        logger.info(f"Total tareas ToDo recuperadas de lista '{list_id}': {len(all_tasks)} ({page_count} pág procesadas).")
        return {"status": "success", "data": all_tasks, "total_retrieved": len(all_tasks), "pages_processed": page_count}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP listando tareas ToDo de lista '{list_id}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error listando tareas ToDo de lista '{list_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al listar tareas ToDo: {type(e).__name__}", "details": str(e)}

def create_task(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Crea una nueva tarea en una lista de ToDo específica."""
    list_id: Optional[str] = params.get("list_id") 
    title: Optional[str] = params.get("title") 
    if not list_id or not title:
        return {"status": "error", "message": "Parámetros 'list_id' y 'title' son requeridos para crear tarea.", "http_status": 400}

    url = f"{constants.GRAPH_API_BASE_URL}/me/todo/lists/{list_id}/tasks"
    body: Dict[str, Any] = {"title": title}
    
    # Poblar campos opcionales directos en el cuerpo de la tarea
    optional_fields_direct = ["importance", "isReminderOn", "status"] 
    # status puede ser: notStarted, inProgress, completed, waitingOnOthers, deferred
    for field in optional_fields_direct:
        if params.get(field) is not None:
            body[field] = params[field]

    # Cuerpo de la tarea (contenido y tipo de contenido)
    if params.get("body_content") and params.get("body_contentType"): # 'text' o 'html'
        body["body"] = {"content": params["body_content"], "contentType": params["body_contentType"]}
    elif params.get("body_content"): # Asumir 'text' si solo se da contenido
        body["body"] = {"content": params["body_content"], "contentType": "text"}
    
    # Campos de fecha/hora. Estos requieren un objeto con dateTime y timeZone.
    datetime_fields_to_parse = {
        "dueDateTime": params.get("dueDateTime"), 
        "reminderDateTime": params.get("reminderDateTime"), 
        "startDateTime": params.get("startDateTime"), # No es un campo estándar de todoTask, pero sí de event/outlookTask
        "completedDateTime": params.get("completedDateTime")
    }
    for field_name, dt_input in datetime_fields_to_parse.items():
        if dt_input:
            try:
                # El input puede ser solo la cadena ISO o un dict {"dateTime": "ISO_STR", "timeZone": "TZ_STR"}
                dt_val_str = dt_input.get("dateTime") if isinstance(dt_input, dict) else dt_input
                dt_tz_str = dt_input.get("timeZone") if isinstance(dt_input, dict) else "UTC" # Default a UTC si no se especifica
                
                parsed_dt_utc_str = _parse_and_utc_datetime_str(dt_val_str, field_name) # Helper normaliza a UTC string Z
                body[field_name] = {"dateTime": parsed_dt_utc_str, "timeZone": "UTC"} # Enviar a Graph como UTC
            except (ValueError, AttributeError) as ve: 
                return {"status": "error", "message": f"Formato inválido para '{field_name}': {ve}", "http_status": 400}

    logger.info(f"Creando tarea ToDo '{title}' en lista '{list_id}'")
    try:
        response = client.post(url, scope=constants.GRAPH_SCOPE, json_data=body)
        task_data = response.json()
        return {"status": "success", "data": task_data, "message": "Tarea ToDo creada exitosamente."}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP creando tarea ToDo en lista '{list_id}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error creando tarea ToDo en lista '{list_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al crear tarea ToDo: {type(e).__name__}", "details": str(e)}

def get_task(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Obtiene una tarea específica de una lista de ToDo."""
    list_id: Optional[str] = params.get("list_id")
    task_id: Optional[str] = params.get("task_id")
    if not list_id or not task_id:
        return {"status": "error", "message": "Parámetros 'list_id' y 'task_id' son requeridos.", "http_status": 400}

    url = f"{constants.GRAPH_API_BASE_URL}/me/todo/lists/{list_id}/tasks/{task_id}"
    query_api_params: Dict[str, Any] = {}
    if params.get('select'): 
        query_api_params['$select'] = params.get('select')
    
    logger.info(f"Obteniendo tarea ToDo '{task_id}' de lista '{list_id}'")
    try:
        response = client.get(url, scope=constants.GRAPH_SCOPE, params=query_api_params if query_api_params else None)
        task_data = response.json()
        return {"status": "success", "data": task_data}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP obteniendo tarea ToDo '{task_id}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        if status_code_resp == 404:
            return {"status": "error", "message": f"Tarea ToDo '{task_id}' en lista '{list_id}' no encontrada.", "details": error_details, "http_status": 404}
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error obteniendo tarea ToDo '{task_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al obtener tarea ToDo: {type(e).__name__}", "details": str(e)}

def update_task(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Actualiza una tarea específica en una lista de ToDo."""
    list_id: Optional[str] = params.get("list_id")
    task_id: Optional[str] = params.get("task_id")
    update_payload: Optional[Dict[str, Any]] = params.get("update_payload")
    if not list_id or not task_id or not update_payload or not isinstance(update_payload, dict):
        return {"status": "error", "message": "Parámetros 'list_id', 'task_id', y 'update_payload' (dict) son requeridos.", "http_status": 400}

    url = f"{constants.GRAPH_API_BASE_URL}/me/todo/lists/{list_id}/tasks/{task_id}"
    
    # Copiar el payload para no modificar el original y procesar fechas.
    body_update = update_payload.copy()
    try: 
        datetime_fields_to_parse = ["dueDateTime", "reminderDateTime", "startDateTime", "completedDateTime"]
        for field_name in datetime_fields_to_parse:
            if field_name in body_update and body_update[field_name]: # Si el campo existe y no es None/vacío
                dt_input = body_update[field_name]
                dt_val_str = dt_input.get("dateTime") if isinstance(dt_input, dict) else dt_input
                # dt_tz_str = dt_input.get("timeZone") if isinstance(dt_input, dict) else "UTC" # No es necesario aquí, helper maneja
                
                parsed_dt_utc_str = _parse_and_utc_datetime_str(dt_val_str, f"update_payload.{field_name}")
                body_update[field_name] = {"dateTime": parsed_dt_utc_str, "timeZone": "UTC"}
            elif field_name in body_update and body_update[field_name] is None: # Permitir borrar fechas pasandolas como null
                body_update[field_name] = None


    except ValueError as ve: 
        return {"status": "error", "message": f"Error en formato de fecha en 'update_payload': {ve}", "http_status": 400}
            
    logger.info(f"Actualizando tarea ToDo '{task_id}' en lista '{list_id}' con payload: {body_update}")
    try:
        response = client.patch(url, scope=constants.GRAPH_SCOPE, json_data=body_update)
        # ToDo task PATCH devuelve el objeto actualizado
        updated_task_data = response.json()
        return {"status": "success", "data": updated_task_data, "message": f"Tarea ToDo '{task_id}' actualizada."}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP actualizando tarea ToDo '{task_id}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error actualizando tarea ToDo '{task_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al actualizar tarea ToDo: {type(e).__name__}", "details": str(e)}

def delete_task(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Elimina una tarea específica de una lista de ToDo."""
    list_id: Optional[str] = params.get("list_id")
    task_id: Optional[str] = params.get("task_id")
    if not list_id or not task_id:
        return {"status": "error", "message": "Parámetros 'list_id' y 'task_id' son requeridos.", "http_status": 400}

    url = f"{constants.GRAPH_API_BASE_URL}/me/todo/lists/{list_id}/tasks/{task_id}"
    logger.info(f"Eliminando tarea ToDo '{task_id}' de lista '{list_id}'")
    try:
        response = client.delete(url, scope=constants.GRAPH_SCOPE) # No necesita headers especiales para ToDo delete
        if response.status_code == 204: # Éxito
            return {"status": "success", "message": f"Tarea ToDo '{task_id}' eliminada exitosamente."}
        else:
            error_details = response.text[:200] if hasattr(response, 'text') else "Respuesta inesperada."
            logger.error(f"Respuesta inesperada {response.status_code} al eliminar tarea ToDo '{task_id}': {error_details}")
            return {"status": "error", "message": f"Respuesta inesperada {response.status_code} al eliminar tarea.", "details": error_details, "http_status": response.status_code}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP eliminando tarea ToDo '{task_id}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error eliminando tarea ToDo '{task_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al eliminar tarea ToDo: {type(e).__name__}", "details": str(e)}


# --- Funciones NO mapeadas en ACTION_MAP actualmente (mantenidas del código original con su prefijo) ---

def todo_update_task_list(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Actualiza una lista de tareas de ToDo específica."""
    list_id: Optional[str] = params.get("list_id")
    update_payload: Optional[Dict[str, Any]] = params.get("update_payload") # ej: {"displayName": "Nuevo Nombre"}
    if not list_id or not update_payload or not isinstance(update_payload, dict):
        return {"status": "error", "message": "Parámetros 'list_id' y 'update_payload' (dict) requeridos.", "http_status": 400}
    
    url = f"{constants.GRAPH_API_BASE_URL}/me/todo/lists/{list_id}"
    logger.info(f"Actualizando lista de ToDo '{list_id}' con payload: {update_payload}")
    try:
        response = client.patch(url, scope=constants.GRAPH_SCOPE, json_data=update_payload)
        if response.status_code == 204: # No Content, común en PATCH si no hay cambios o no se devuelve cuerpo
            logger.info(f"Lista ToDo '{list_id}' actualizada (204 No Content). Re-obteniendo para confirmar...")
            # Para obtener datos actualizados, hacemos un GET
            get_response = client.get(url, scope=constants.GRAPH_SCOPE, params={"$select":"id,displayName,isOwner,isShared,wellknownListName"})
            updated_list_data = get_response.json()
            return {"status": "success", "message": f"Lista ToDo '{list_id}' actualizada.", "data": updated_list_data}
        
        updated_list_data = response.json() # 200 OK con el objeto actualizado
        return {"status": "success", "data": updated_list_data, "message": f"Lista ToDo '{list_id}' actualizada."}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP actualizando lista ToDo '{list_id}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error actualizando lista ToDo '{list_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al actualizar lista ToDo: {type(e).__name__}", "details": str(e)}

def todo_delete_task_list(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Elimina una lista de tareas de ToDo específica."""
    list_id: Optional[str] = params.get("list_id")
    if not list_id: 
        return {"status": "error", "message": "Parámetro 'list_id' es requerido.", "http_status": 400}
    
    url = f"{constants.GRAPH_API_BASE_URL}/me/todo/lists/{list_id}"
    logger.info(f"Eliminando lista de ToDo '{list_id}'")
    try:
        response = client.delete(url, scope=constants.GRAPH_SCOPE)
        if response.status_code == 204:
            return {"status": "success", "message": f"Lista ToDo '{list_id}' eliminada exitosamente."}
        else:
            error_details = response.text[:200] if hasattr(response, 'text') else "Respuesta inesperada."
            logger.error(f"Respuesta inesperada {response.status_code} al eliminar lista ToDo '{list_id}': {error_details}")
            return {"status": "error", "message": f"Respuesta inesperada {response.status_code} al eliminar lista ToDo.", "details": error_details, "http_status": response.status_code}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP eliminando lista ToDo '{list_id}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error eliminando lista ToDo '{list_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al eliminar lista ToDo: {type(e).__name__}", "details": str(e)}

def todo_complete_task(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Marca una tarea ToDo como completada."""
    list_id: Optional[str] = params.get("list_id")
    task_id: Optional[str] = params.get("task_id")
    if not list_id or not task_id:
        return {"status": "error", "message": "Parámetros 'list_id' y 'task_id' son requeridos para completar tarea.", "http_status": 400}
    
    logger.info(f"Marcando tarea ToDo '{task_id}' en lista '{list_id}' como completada.")
    
    # El payload para completar una tarea incluye el estado y la fecha de completado.
    current_utc_time_str = datetime.now(dt_timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    payload_complete = {
        "status": "completed",
        "completedDateTime": {
            "dateTime": current_utc_time_str,
            "timeZone": "UTC"
        }
    }
    # Reutilizar la función update_task (la que tiene el nombre corto, mapeada)
    update_params = {"list_id": list_id, "task_id": task_id, "update_payload": payload_complete}
    
    # Llamar a la función update_task (nombre corto)
    update_result = update_task(client, update_params) 
    
    if update_result.get("status") == "success":
        update_result["message"] = f"Tarea ToDo '{task_id}' marcada como completada." # Sobrescribir mensaje
    
    return update_result

# --- FIN DEL MÓDULO actions/todo_actions.py ---