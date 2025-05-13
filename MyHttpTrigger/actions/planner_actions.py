# MyHttpTrigger/actions/planner_actions.py
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
# (Mantenido aquí ya que es específico para el manejo de fechas en Planner)
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

# ==================================
# ==== FUNCIONES ACCIÓN PLANNER ====
# ==================================

# --- Funciones mapeadas en ACTION_MAP (nombres corregidos) ---

def list_plans(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    owner_type: str = params.get("owner_type", "user").lower()
    owner_id: Optional[str] = params.get("owner_id")
    
    if owner_type == "group" and not owner_id:
        return {"status": "error", "message": "Si 'owner_type' es 'group', se requiere 'owner_id'.", "http_status": 400}
    
    url: str
    log_owner_description: str
    if owner_type == "user": 
        url = f"{constants.GRAPH_API_BASE_URL}/me/planner/plans"
        log_owner_description = "usuario actual (/me)"
    elif owner_type == "group": 
        url = f"{constants.GRAPH_API_BASE_URL}/groups/{owner_id}/planner/plans"
        log_owner_description = f"grupo '{owner_id}'"
    else: 
        return {"status": "error", "message": "Parámetro 'owner_type' debe ser 'user' o 'group'.", "http_status": 400}
            
    top: int = min(int(params.get("top", 25)), constants.MAX_GRAPH_TOP_VALUE) # Usar constante para max top
    query_api_params: Dict[str, Any] = {'$top': top}
    
    default_select = "id,title,owner,createdDateTime,container" # container es útil
    query_api_params['$select'] = params.get('select', default_select)
    if params.get('filter'): 
        query_api_params['$filter'] = params.get('filter')

    logger.info(f"Listando planes de Planner para {log_owner_description} (Top: {top}, Select: {query_api_params['$select']})")
    try:
        response = client.get(url, scope=constants.GRAPH_SCOPE, params=query_api_params)
        plans_data = response.json()
        return {"status": "success", "data": plans_data.get("value", [])}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        logger.error(f"Error HTTP listando planes Planner para {log_owner_description}: {http_err.response.status_code if http_err.response else 'N/A'} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {http_err.response.status_code if http_err.response else 'N/A'}", "details": error_details, "http_status": http_err.response.status_code if http_err.response else 500}
    except Exception as e:
        logger.error(f"Error listando planes Planner para {log_owner_description}: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al listar planes: {type(e).__name__}", "details": str(e)}

def get_plan(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    plan_id: Optional[str] = params.get("plan_id")
    if not plan_id: 
        return {"status": "error", "message": "Parámetro 'plan_id' es requerido.", "http_status": 400}
    
    url = f"{constants.GRAPH_API_BASE_URL}/planner/plans/{plan_id}"
    query_api_params: Dict[str, Any] = {}
    if params.get('select'): 
        query_api_params['$select'] = params.get('select')
    else: # Select por defecto con campos útiles
        query_api_params['$select'] = "id,title,owner,createdDateTime,container,details"


    logger.info(f"Obteniendo detalles del plan de Planner '{plan_id}'")
    try:
        response = client.get(url, scope=constants.GRAPH_SCOPE, params=query_api_params if query_api_params else None)
        plan_data = response.json()
        return {"status": "success", "data": plan_data}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP obteniendo plan Planner '{plan_id}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        if status_code_resp == 404:
            return {"status": "error", "message": f"Plan '{plan_id}' no encontrado.", "details": error_details, "http_status": 404}
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error obteniendo plan Planner '{plan_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al obtener plan: {type(e).__name__}", "details": str(e)}

def list_tasks(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    plan_id: Optional[str] = params.get("plan_id")
    if not plan_id: 
        return {"status": "error", "message": "Parámetro 'plan_id' es requerido para listar tareas.", "http_status": 400}

    # Paginación y filtros
    top_per_page: int = min(int(params.get('top_per_page', 25)), constants.MAX_GRAPH_TOP_VALUE_PAGING)
    max_items_total: int = int(params.get('max_items_total', 100)) # Límite total de items a devolver
    select: Optional[str] = params.get('select')
    filter_query: Optional[str] = params.get('filter_query')
    order_by: Optional[str] = params.get('order_by')

    url_base = f"{constants.GRAPH_API_BASE_URL}/planner/plans/{plan_id}/tasks"
    query_api_params_initial: Dict[str, Any] = {'$top': top_per_page}
    if select: query_api_params_initial['$select'] = select
    else: query_api_params_initial['$select'] = "id,title,percentComplete,priority,dueDateTime,assigneePriority,assignments,bucketId,planId,orderHint"
    if filter_query: query_api_params_initial['$filter'] = filter_query
    if order_by: query_api_params_initial['$orderby'] = order_by
    
    all_tasks: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0
    
    logger.info(f"Listando tareas del plan Planner '{plan_id}' (Max total: {max_items_total}, Por pág: {top_per_page})")
    try:
        while current_url and len(all_tasks) < max_items_total:
            page_count += 1
            # Aplicar parámetros de query solo en la primera llamada si son para la base
            # Las URLs @odata.nextLink ya incluyen sus propios parámetros.
            current_call_params = query_api_params_initial if page_count == 1 else None
            
            logger.debug(f"Obteniendo página {page_count} de tareas desde: {current_url} con params: {current_call_params}")
            response = client.get(current_url, scope=constants.GRAPH_SCOPE, params=current_call_params)
            response_data = response.json()
            
            page_items = response_data.get('value', [])
            if not isinstance(page_items, list):
                logger.warning(f"Respuesta inesperada para tareas página {page_count}, 'value' no es una lista.")
                break
            
            for item in page_items:
                if len(all_tasks) < max_items_total:
                    all_tasks.append(item)
                else:
                    break # Alcanzado max_items_total
            
            current_url = response_data.get('@odata.nextLink')
            if not current_url:
                logger.debug("No hay más páginas de tareas (@odata.nextLink no presente).")
                break
            if len(all_tasks) >= max_items_total:
                logger.debug(f"Alcanzado límite de 'max_items_total' ({max_items_total}).")
                break
                
        logger.info(f"Total tareas Planner recuperadas para plan '{plan_id}': {len(all_tasks)} ({page_count} pág procesadas).")
        return {"status": "success", "data": all_tasks, "total_retrieved": len(all_tasks), "pages_processed": page_count}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP listando tareas Planner del plan '{plan_id}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error listando tareas Planner del plan '{plan_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al listar tareas Planner: {type(e).__name__}", "details": str(e)}

def create_task(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    plan_id: Optional[str] = params.get("plan_id")
    title: Optional[str] = params.get("title")
    if not plan_id or not title:
        return {"status": "error", "message": "Parámetros 'plan_id' y 'title' son requeridos para crear tarea.", "http_status": 400}

    bucket_id: Optional[str] = params.get("bucket_id")
    assignments: Optional[Dict[str, Any]] = params.get("assignments") # ej: {"userId1": {"@odata.type":"#microsoft.graph.plannerAssignment", "orderHint":" !"}, ...}
    due_datetime_str: Optional[str] = params.get("dueDateTime")
    # Para crear detalles de tarea (descripción, checklist, referencias) se hace un PATCH posterior a /planner/tasks/{taskId}/details
    # Esta función crea la tarea principal. El payload de detalles se puede pasar para una actualización inmediata.
    details_payload: Optional[Dict[str, Any]] = params.get("details_payload") # ej: {"description": "...", "references": {...}, "checklist": {...}}

    url_task = f"{constants.GRAPH_API_BASE_URL}/planner/tasks"
    body: Dict[str, Any] = {"planId": plan_id, "title": title}
    if bucket_id: 
        body["bucketId"] = bucket_id
    if assignments and isinstance(assignments, dict): 
        body["assignments"] = assignments
    if due_datetime_str:
        try: 
            body["dueDateTime"] = _parse_and_utc_datetime_str(due_datetime_str, "dueDateTime")
        except ValueError as ve: 
            return {"status": "error", "message": f"Formato inválido para 'dueDateTime': {ve}", "http_status": 400}
    
    # Otros campos opcionales directos en la tarea: priority, percentComplete, startDate, etc.
    optional_fields = ["priority", "percentComplete", "startDateTime", "assigneePriority", "orderHint"]
    for field in optional_fields:
        if params.get(field) is not None:
            if field.endswith("DateTime"):
                try: body[field] = _parse_and_utc_datetime_str(params[field], field)
                except ValueError as ve: return {"status": "error", "message": f"Formato inválido para '{field}': {ve}", "http_status": 400}
            else:
                body[field] = params[field]
    
    logger.info(f"Creando tarea Planner '{title}' en plan '{plan_id}'")
    try:
        response_task = client.post(url_task, scope=constants.GRAPH_SCOPE, json_data=body)
        task_data = response_task.json()
        task_id = task_data.get("id")
        
        if details_payload and isinstance(details_payload, dict) and task_id:
            logger.info(f"Tarea Planner '{task_id}' creada. Procediendo a actualizar detalles.")
            details_url = f"{constants.GRAPH_API_BASE_URL}/planner/tasks/{task_id}/details"
            
            # Para actualizar detalles, se necesita el ETag de los detalles. Lo obtenemos de la tarea creada si incluye 'details'.
            # O hacemos un GET previo a los detalles para obtener el ETag.
            etag_details = task_data.get("details", {}).get("@odata.etag")
            if not etag_details:
                try:
                    logger.debug(f"ETag de detalles no en respuesta de creación. Obteniendo ETag para detalles de tarea '{task_id}'.")
                    get_details_response = client.get(details_url, scope=constants.GRAPH_SCOPE, params={"$select": "@odata.etag"})
                    etag_details = get_details_response.json().get("@odata.etag")
                except requests.exceptions.HTTPError as http_e_details:
                    if http_e_details.response and http_e_details.response.status_code == 404: # Puede que aún no existan detalles
                        etag_details = None 
                        logger.info(f"Detalles para tarea '{task_id}' no encontrados (404), se crearán con PATCH.")
                    else: # Otro error al obtener ETag
                        logger.warning(f"No se pudo obtener ETag para detalles de tarea '{task_id}' debido a error HTTP: {http_e_details}. Se intentará PATCH sin ETag.")
                        etag_details = None # Proceder sin ETag
                except Exception as get_etag_err:
                    logger.warning(f"Error obteniendo ETag para detalles de tarea '{task_id}': {get_etag_err}. Se intentará PATCH sin ETag.")
                    etag_details = None

            details_custom_headers = {}
            if etag_details: 
                details_custom_headers['If-Match'] = etag_details
            else: # Si no hay ETag (ej. detalles aún no existen), Graph debería permitir el PATCH para crearlos.
                logger.info(f"Actualizando detalles de tarea '{task_id}' sin ETag (posiblemente creando detalles).")

            # PATCH para actualizar/crear los detalles
            details_response = client.patch(details_url, scope=constants.GRAPH_SCOPE, json_data=details_payload, headers=details_custom_headers)
            task_data["details"] = details_response.json() # Adjuntar detalles actualizados
            task_data["details_update_status"] = "success"
            logger.info(f"Detalles de tarea Planner '{task_id}' actualizados/creados.")

        return {"status": "success", "data": task_data, "message": "Tarea Planner creada."}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP creando tarea Planner: {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error creando tarea Planner: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al crear tarea Planner: {type(e).__name__}", "details": str(e)}

def get_task(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    task_id: Optional[str] = params.get("task_id")
    if not task_id: 
        return {"status": "error", "message": "Parámetro 'task_id' es requerido.", "http_status": 400}
    
    url = f"{constants.GRAPH_API_BASE_URL}/planner/tasks/{task_id}"
    query_api_params: Dict[str, Any] = {}
    if params.get('select'): 
        query_api_params['$select'] = params.get('select')
    if params.get('expand_details', str(params.get('expand', "")).lower() == 'details'): # Aceptar 'expand_details' o 'expand':'details'
        query_api_params['$expand'] = 'details'
        if query_api_params.get('$select') and 'details' not in query_api_params['$select']:
            query_api_params['$select'] += ",details" # Asegurar que details se selecciona si se expande

    logger.info(f"Obteniendo tarea Planner '{task_id}'")
    try:
        response = client.get(url, scope=constants.GRAPH_SCOPE, params=query_api_params if query_api_params else None)
        task_data = response.json()
        return {"status": "success", "data": task_data}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP obteniendo tarea Planner '{task_id}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        if status_code_resp == 404:
            return {"status": "error", "message": f"Tarea Planner '{task_id}' no encontrada.", "details": error_details, "http_status": 404}
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error obteniendo tarea Planner '{task_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al obtener tarea Planner: {type(e).__name__}", "details": str(e)}

def update_task(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    task_id: Optional[str] = params.get("task_id")
    if not task_id:
        return {"status": "error", "message": "Parámetro 'task_id' es requerido para actualizar.", "http_status": 400}

    # Payload para la tarea principal y para los detalles de la tarea
    update_payload_task: Optional[Dict[str, Any]] = params.get("update_payload_task") # Campos de plannerTask
    update_payload_details: Optional[Dict[str, Any]] = params.get("update_payload_details") # Campos de plannerTaskDetails

    # ETags son cruciales para Planner para evitar sobrescrituras accidentales
    etag_task: Optional[str] = params.get("etag_task") # ETag para el objeto plannerTask
    etag_details: Optional[str] = params.get("etag_details") # ETag para el objeto plannerTaskDetails

    if not update_payload_task and not update_payload_details:
        return {"status": "success", "message": "No se especificaron cambios (update_payload_task o update_payload_details están vacíos).", "data": {"id": task_id}}

    final_task_data_response: Dict[str, Any] = {"id": task_id} # Para acumular resultados

    # 1. Actualizar campos de la tarea principal (plannerTask)
    if update_payload_task and isinstance(update_payload_task, dict):
        url_task = f"{constants.GRAPH_API_BASE_URL}/planner/tasks/{task_id}"
        custom_headers_task = {}
        # Usar ETag proporcionado en params o el que venga en el payload
        current_etag_task = etag_task or update_payload_task.pop('@odata.etag', None)
        if current_etag_task: 
            custom_headers_task['If-Match'] = current_etag_task
        else: 
            logger.warning(f"Actualizando tarea Planner '{task_id}' (campos principales) sin ETag. Se recomienda obtener y enviar ETag.")
        
        # Convertir fechas si están presentes en el payload de la tarea
        for field in ["dueDateTime", "startDateTime"]:
            if field in update_payload_task and update_payload_task[field]:
                try: update_payload_task[field] = _parse_and_utc_datetime_str(update_payload_task[field], field)
                except ValueError as ve: return {"status": "error", "message": f"Formato inválido para '{field}' en update_payload_task: {ve}", "http_status": 400}

        logger.info(f"Actualizando tarea Planner '{task_id}' (campos principales). ETag usado: {current_etag_task or 'Ninguno'}")
        try:
            response_task = client.patch(url_task, scope=constants.GRAPH_SCOPE, json_data=update_payload_task, headers=custom_headers_task)
            # Planner PATCH devuelve el objeto actualizado (200 OK) o 204 No Content si ETag coincide y no hay cambios.
            if response_task.status_code == 204:
                logger.info(f"Tarea Planner '{task_id}' actualizada (204 No Content). Re-obteniendo datos para confirmar.")
                # Es buena idea re-obtener la tarea para tener el ETag más reciente y los datos completos.
                get_task_params = {"task_id": task_id}
                if update_payload_details: get_task_params["expand_details"] = True # Si vamos a actualizar detalles, mejor traerlos
                get_task_result = get_task(client, get_task_params)
                if get_task_result["status"] == "success": final_task_data_response = get_task_result["data"]
                else: logger.warning(f"No se pudo re-obtener la tarea '{task_id}' después de PATCH 204: {get_task_result.get('message')}")
            else: # 200 OK
                final_task_data_response = response_task.json()
            logger.info(f"Campos principales de tarea '{task_id}' actualizados.")
            final_task_data_response["task_update_status"] = "success"
        except requests.exceptions.HTTPError as http_err_task:
            error_details_task = http_err_task.response.text if http_err_task.response else "No response body"
            status_code_task = http_err_task.response.status_code if http_err_task.response else 500
            logger.error(f"Error HTTP actualizando campos principales de tarea Planner '{task_id}': {status_code_task} - {error_details_task[:200]}", exc_info=False)
            return {"status": "error", "message": f"Error HTTP al actualizar tarea: {status_code_task}", "details": error_details_task, "http_status": status_code_task}
        except Exception as e_task:
            logger.error(f"Error actualizando campos principales de tarea Planner '{task_id}': {type(e_task).__name__} - {e_task}", exc_info=True)
            return {"status": "error", "message": f"Error al actualizar tarea: {type(e_task).__name__}", "details": str(e_task)}

    # 2. Actualizar campos de detalles de la tarea (plannerTaskDetails)
    if update_payload_details and isinstance(update_payload_details, dict):
        url_details = f"{constants.GRAPH_API_BASE_URL}/planner/tasks/{task_id}/details"
        custom_headers_details = {}
        # Usar ETag proporcionado en params, o el que venga en el payload de detalles,
        # o el ETag de los detalles de la tarea si ya la obtuvimos.
        current_etag_details = etag_details or update_payload_details.pop('@odata.etag', None)
        if not current_etag_details and final_task_data_response.get("details"):
            current_etag_details = final_task_data_response.get("details",{}).get("@odata.etag")

        if not current_etag_details: # Si aún no tenemos ETag, intentamos obtenerlo explícitamente
            try:
                logger.debug(f"ETag de detalles no disponible. Obteniendo ETag para detalles de tarea '{task_id}'.")
                get_details_response = client.get(url_details, scope=constants.GRAPH_SCOPE, params={"$select": "@odata.etag"})
                current_etag_details = get_details_response.json().get("@odata.etag")
            except Exception as get_etag_err: # Si falla, procedemos sin ETag para detalles (podría ser creación)
                logger.warning(f"No se pudo obtener ETag para detalles de tarea '{task_id}': {get_etag_err}. Se intentará PATCH sin ETag.")
        
        if current_etag_details: 
            custom_headers_details['If-Match'] = current_etag_details
        else:
            logger.warning(f"Actualizando detalles de tarea Planner '{task_id}' sin ETag. Puede que se estén creando.")

        logger.info(f"Actualizando detalles para tarea Planner '{task_id}'. ETag usado: {current_etag_details or 'Ninguno'}")
        try:
            response_details = client.patch(url_details, scope=constants.GRAPH_SCOPE, json_data=update_payload_details, headers=custom_headers_details)
            # Planner PATCH devuelve el objeto actualizado (200 OK) o 204 No Content
            updated_details_data = {}
            if response_details.status_code == 204:
                logger.info(f"Detalles de tarea Planner '{task_id}' actualizados (204 No Content). Re-obteniendo para confirmar.")
                get_details_params = {"task_id": task_id, "expand_details": True}
                get_task_result_for_details = get_task(client, get_details_params) # Llama a get_task para obtener todo
                if get_task_result_for_details["status"] == "success":
                    updated_details_data = get_task_result_for_details["data"].get("details", {})
                    # Fusionar los detalles actualizados en la respuesta final
                    if "data" in final_task_data_response and isinstance(final_task_data_response["data"], dict):
                        final_task_data_response["data"]["details"] = updated_details_data
                    elif isinstance(final_task_data_response, dict): # Si solo se actualizó la tarea principal antes
                         final_task_data_response["details"] = updated_details_data

            else: # 200 OK
                 updated_details_data = response_details.json()
                 # Fusionar los detalles actualizados en la respuesta final
                 if "data" in final_task_data_response and isinstance(final_task_data_response["data"], dict):
                     final_task_data_response["data"]["details"] = updated_details_data
                 elif isinstance(final_task_data_response, dict): # Si solo se actualizó la tarea principal antes
                      final_task_data_response["details"] = updated_details_data

            logger.info(f"Detalles de tarea '{task_id}' actualizados.")
            # Añadir un estado de actualización de detalles a la respuesta
            if isinstance(final_task_data_response, dict):
                final_task_data_response["details_update_status"] = "success"

        except requests.exceptions.HTTPError as http_err_details:
            error_details_val = http_err_details.response.text if http_err_details.response else "No response body"
            status_code_details = http_err_details.response.status_code if http_err_details.response else 500
            logger.error(f"Error HTTP actualizando detalles de tarea Planner '{task_id}': {status_code_details} - {error_details_val[:200]}", exc_info=False)
            if isinstance(final_task_data_response, dict): final_task_data_response["details_update_status"] = f"error: {status_code_details}"
            # No retornar aquí si la actualización de la tarea principal fue exitosa, solo registrar el error de detalles.
            # Pero si es el único payload, entonces sí es un error completo.
            if not update_payload_task:
                return {"status": "error", "message": f"Error HTTP al actualizar detalles: {status_code_details}", "details": error_details_val, "http_status": status_code_details}
        except Exception as e_details:
            logger.error(f"Error actualizando detalles de tarea Planner '{task_id}': {type(e_details).__name__} - {e_details}", exc_info=True)
            if isinstance(final_task_data_response, dict): final_task_data_response["details_update_status"] = f"error: {type(e_details).__name__}"
            if not update_payload_task:
                return {"status": "error", "message": f"Error al actualizar detalles: {type(e_details).__name__}", "details": str(e_details)}
            
    return {"status": "success", "data": final_task_data_response, "message": "Actualización de tarea Planner y/o detalles procesada."}

def delete_task(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    task_id: Optional[str] = params.get("task_id")
    etag: Optional[str] = params.get("etag") # ETag del objeto plannerTask
    if not task_id: 
        return {"status": "error", "message": "Parámetro 'task_id' es requerido.", "http_status": 400}

    url = f"{constants.GRAPH_API_BASE_URL}/planner/tasks/{task_id}"
    custom_headers = {}
    if etag: 
        custom_headers['If-Match'] = etag
        logger.info(f"Eliminando tarea Planner '{task_id}' con ETag '{etag}'.")
    else: 
        logger.warning(f"Eliminando tarea Planner '{task_id}' sin ETag. Se recomienda obtener y enviar ETag (puede fallar u operar sobre datos obsoletos).")
    
    logger.info(f"Intentando eliminar tarea Planner '{task_id}'")
    try:
        response = client.delete(url, scope=constants.GRAPH_SCOPE, headers=custom_headers)
        # Planner DELETE devuelve 204 No Content si tiene éxito
        if response.status_code == 204:
            return {"status": "success", "message": f"Tarea Planner '{task_id}' eliminada exitosamente."}
        else: # Respuesta inesperada
            logger.error(f"Respuesta inesperada {response.status_code} al eliminar tarea Planner '{task_id}': {response.text[:200]}")
            return {"status": "error", "message": f"Respuesta inesperada {response.status_code} al eliminar tarea.", "details": response.text, "http_status": response.status_code}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP eliminando tarea Planner '{task_id}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error eliminando tarea Planner '{task_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al eliminar tarea Planner: {type(e).__name__}", "details": str(e)}

def list_buckets(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    plan_id: Optional[str] = params.get("plan_id")
    if not plan_id: 
        return {"status": "error", "message": "Parámetro 'plan_id' es requerido para listar buckets.", "http_status": 400}

    url = f"{constants.GRAPH_API_BASE_URL}/planner/plans/{plan_id}/buckets"
    query_api_params: Dict[str, Any] = {}
    if params.get('select'): 
        query_api_params['$select'] = params.get('select')
    else: # Select por defecto
        query_api_params['$select'] = "id,name,orderHint,planId"
    if params.get('filter'): 
        query_api_params['$filter'] = params.get('filter')
    # $top no es comúnmente usado para buckets ya que los planes no suelen tener cientos, pero se podría añadir.

    logger.info(f"Listando buckets para el plan Planner '{plan_id}'")
    try:
        response = client.get(url, scope=constants.GRAPH_SCOPE, params=query_api_params if query_api_params else None)
        buckets_data = response.json()
        return {"status": "success", "data": buckets_data.get("value", [])}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP listando buckets del plan '{plan_id}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error listando buckets del plan '{plan_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al listar buckets: {type(e).__name__}", "details": str(e)}

def create_bucket(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    plan_id: Optional[str] = params.get("plan_id")
    name: Optional[str] = params.get("name") # Nombre del bucket
    if not plan_id or not name:
        return {"status": "error", "message": "Parámetros 'plan_id' y 'name' (nombre del bucket) son requeridos.", "http_status": 400}

    order_hint: Optional[str] = params.get("orderHint") # Opcional, para controlar el orden

    url = f"{constants.GRAPH_API_BASE_URL}/planner/buckets"
    body: Dict[str, Any] = {"name": name, "planId": plan_id}
    if order_hint:
        body["orderHint"] = order_hint
    
    logger.info(f"Creando bucket '{name}' en plan Planner '{plan_id}'")
    try:
        response = client.post(url, scope=constants.GRAPH_SCOPE, json_data=body)
        bucket_data = response.json()
        return {"status": "success", "data": bucket_data, "message": "Bucket creado exitosamente."}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP creando bucket en plan '{plan_id}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error creando bucket en plan '{plan_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al crear bucket: {type(e).__name__}", "details": str(e)}

# --- Funciones NO mapeadas en ACTION_MAP actualmente (mantenidas del código original con su prefijo) ---
# Si se añaden al ACTION_MAP con nombres cortos, se deberían renombrar como las anteriores.

def planner_create_plan(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    title: Optional[str] = params.get("title")
    # owner_id es el ID del grupo al que pertenecerá el plan.
    owner_group_id: Optional[str] = params.get("owner_group_id") 
    if not title or not owner_group_id:
        return {"status": "error", "message": "Parámetros 'title' y 'owner_group_id' son requeridos para crear plan.", "http_status": 400}
    
    url = f"{constants.GRAPH_API_BASE_URL}/planner/plans"
    # El 'owner' en el cuerpo es el ID del grupo.
    body = {"owner": owner_group_id, "title": title}

    # Opcionalmente, se puede especificar 'container' para vincularlo a otros recursos, 
    # pero 'owner' (group ID) es lo más común para empezar.
    # container_url: Optional[str] = params.get("container_url") # ej. /planner/rosters/{roster-id}
    # if container_url:
    #    body["container"] = {"url": container_url, "@odata.type": "#microsoft.graph.plannerPlanContainer"}


    logger.info(f"Creando plan de Planner '{title}' para grupo '{owner_group_id}'")
    try:
        response = client.post(url, scope=constants.GRAPH_SCOPE, json_data=body)
        created_plan = response.json()
        return {"status": "success", "data": created_plan, "message": "Plan creado exitosamente."}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP creando plan Planner: {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error creando plan Planner: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al crear plan: {type(e).__name__}", "details": str(e)}

def planner_update_plan(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    plan_id: Optional[str] = params.get("plan_id")
    update_payload: Optional[Dict[str, Any]] = params.get("update_payload") # Campos a actualizar, ej {"title": "Nuevo Título"}
    etag: Optional[str] = params.get("etag") # ETag del plan
    if not plan_id or not update_payload or not isinstance(update_payload, dict):
        return {"status": "error", "message": "Parámetros 'plan_id' y 'update_payload' (dict) son requeridos. 'etag' es recomendado.", "http_status": 400}

    url = f"{constants.GRAPH_API_BASE_URL}/planner/plans/{plan_id}"
    custom_headers = {}
    final_etag = etag or update_payload.pop('@odata.etag', None) # Tomar etag de params o del payload
    if final_etag: 
        custom_headers['If-Match'] = final_etag
        logger.info(f"Usando ETag '{final_etag}' para actualizar plan '{plan_id}'")
    else: 
        logger.warning(f"Actualizando plan '{plan_id}' sin ETag. Se recomienda encarecidamente usar ETag.")

    logger.info(f"Actualizando plan de Planner '{plan_id}' con payload: {update_payload}")
    try:
        response = client.patch(url, scope=constants.GRAPH_SCOPE, json_data=update_payload, headers=custom_headers)
        if response.status_code == 204: # No Content si el ETag coincidió y no hubo cambios aplicables o no se devolvió contenido
             logger.info(f"Plan '{plan_id}' actualizado (204 No Content). Obteniendo datos actualizados...")
             # Re-obtener el plan para devolver los datos actualizados
             get_plan_result = get_plan(client, {"plan_id": plan_id}) # Llama a la función get_plan (nombre corto)
             if get_plan_result["status"] == "success":
                 return {"status": "success", "data": get_plan_result["data"], "message": f"Plan '{plan_id}' actualizado."}
             else: # Fallo al re-obtener
                 return {"status": "success", "message": f"Plan '{plan_id}' actualizado (204), pero falló la re-obtención.", "data": {"id": plan_id, "@odata.etag": response.headers.get("ETag")}}

        updated_plan_data = response.json() # 200 OK con el plan actualizado
        return {"status": "success", "data": updated_plan_data, "message": f"Plan '{plan_id}' actualizado."}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP actualizando plan Planner '{plan_id}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error actualizando plan Planner '{plan_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al actualizar plan: {type(e).__name__}", "details": str(e)}

def planner_delete_plan(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    plan_id: Optional[str] = params.get("plan_id")
    etag: Optional[str] = params.get("etag") # ETag del plan
    if not plan_id: 
        return {"status": "error", "message": "Parámetro 'plan_id' es requerido para eliminar plan.", "http_status": 400}

    url = f"{constants.GRAPH_API_BASE_URL}/planner/plans/{plan_id}"
    custom_headers = {}
    if etag: 
        custom_headers['If-Match'] = etag
        logger.info(f"Eliminando plan '{plan_id}' con ETag '{etag}'.")
    else: 
        # Aunque no es estrictamente requerido por la API para DELETE, es una buena práctica si se tiene.
        # Planner API para DELETE no parece requerir ETag, a diferencia de PATCH.
        logger.warning(f"Eliminando plan '{plan_id}' sin ETag.") 
    
    logger.info(f"Intentando eliminar plan de Planner '{plan_id}'")
    try:
        response = client.delete(url, scope=constants.GRAPH_SCOPE, headers=custom_headers)
        if response.status_code == 204: # Éxito
            return {"status": "success", "message": f"Plan '{plan_id}' eliminado exitosamente."}
        else:
            error_details = response.text[:200] if hasattr(response, 'text') else "Respuesta inesperada."
            logger.error(f"Respuesta inesperada {response.status_code} al eliminar plan Planner '{plan_id}': {error_details}")
            return {"status": "error", "message": f"Respuesta inesperada {response.status_code} al eliminar plan.", "details": error_details, "http_status": response.status_code}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP eliminando plan Planner '{plan_id}': {status_code_resp} - {error_details[:200]}", exc_info=False)
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error eliminando plan Planner '{plan_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al eliminar plan: {type(e).__name__}", "details": str(e)}

# --- FIN DEL MÓDULO actions/planner_actions.py ---