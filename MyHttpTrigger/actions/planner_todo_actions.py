# MyHttpTrigger/actions/planner_todo_actions.py
import logging
import requests # Solo para tipos de excepción
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone as dt_timezone # Renombrar para claridad

# Importar helper y constantes
try:
    from ..shared.helpers.http_client import hacer_llamada_api
    from ..shared.constants import BASE_URL, GRAPH_API_DEFAULT_TIMEOUT, APP_NAME
except ImportError as e:
    logging.critical(f"Error CRÍTICO importando dependencias compartidas en Planner/ToDo: {e}.", exc_info=True)
    BASE_URL = "https://graph.microsoft.com/v1.0"
    GRAPH_API_DEFAULT_TIMEOUT = 45
    APP_NAME = "EliteDynamicsPro" # Fallback
    raise ImportError(f"No se pudo importar 'hacer_llamada_api' o constantes: {e}") from e

logger = logging.getLogger(f"{APP_NAME}.actions.planner_todo")

# ==================================
# ==== FUNCIONES ACCIÓN PLANNER ====
# ==================================
# Requieren permisos como Group.ReadWrite.All, Tasks.ReadWrite (Planner), etc.

def listar_planes(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    owner_type: str = parametros.get("owner_type", "user").lower()
    owner_id: Optional[str] = parametros.get("owner_id")
    if owner_type == "group" and not owner_id:
        return {"status": "error", "message": "Si 'owner_type' es 'group', se requiere 'owner_id'."}
    
    if owner_type == "user": url = f"{BASE_URL}/me/planner/plans"; log_owner = "/me"
    elif owner_type == "group": url = f"{BASE_URL}/groups/{owner_id}/planner/plans"; log_owner = f"grupo '{owner_id}'"
    else: return {"status": "error", "message": "Parámetro 'owner_type' debe ser 'user' o 'group'."}
        
    top: int = min(int(parametros.get("top", 25)), 999)
    params_query = {'$top': top, '$select': parametros.get('select', 'id,title,owner,createdDateTime')}

    logger.info(f"Listando planes de Planner para {log_owner} (Top: {top})")
    try:
        # Nota: La paginación completa con @odata.nextLink podría añadirse si se esperan muchos planes
        plans_data = hacer_llamada_api("GET", url, headers, params=params_query, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": plans_data.get("value", []) if isinstance(plans_data, dict) else plans_data}
    except Exception as e:
        logger.error(f"Error listando planes Planner para {log_owner}: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al listar planes: {type(e).__name__}", "http_status": status_code, "details": details}

def obtener_plan(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    plan_id: Optional[str] = parametros.get("plan_id")
    if not plan_id: return {"status": "error", "message": "Parámetro 'plan_id' es requerido."}
    url = f"{BASE_URL}/planner/plans/{plan_id}"
    logger.info(f"Obteniendo detalles del plan de Planner '{plan_id}'")
    try:
        plan_data = hacer_llamada_api("GET", url, headers, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": plan_data}
    except Exception as e:
        logger.error(f"Error obteniendo plan Planner '{plan_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            if status_code == 404: return {"status": "error", "message": f"Plan '{plan_id}' no encontrado.", "details": details}
        return {"status": "error", "message": f"Error al obtener plan: {type(e).__name__}", "http_status": status_code, "details": details}

def crear_plan(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    nombre_plan: Optional[str] = parametros.get("nombre_plan")
    grupo_id_owner: Optional[str] = parametros.get("grupo_id_owner")
    if not nombre_plan or not grupo_id_owner:
        return {"status": "error", "message": "Parámetros 'nombre_plan' y 'grupo_id_owner' son requeridos."}
    
    url = f"{BASE_URL}/planner/plans"
    body = {"owner": grupo_id_owner, "title": nombre_plan}
    logger.info(f"Creando plan de Planner '{nombre_plan}' para grupo '{grupo_id_owner}'")
    try:
        created_plan = hacer_llamada_api("POST", url, headers, json_data=body, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": created_plan, "message": "Plan creado exitosamente."}
    except Exception as e:
        logger.error(f"Error creando plan Planner: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al crear plan: {type(e).__name__}", "http_status": status_code, "details": details}

def actualizar_plan(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    plan_id: Optional[str] = parametros.get("plan_id")
    nuevos_valores: Optional[Dict[str, Any]] = parametros.get("nuevos_valores")
    etag: Optional[str] = parametros.get("etag")
    if not plan_id or not nuevos_valores or not isinstance(nuevos_valores, dict):
        return {"status": "error", "message": "Params 'plan_id' y 'nuevos_valores' (dict) requeridos."}

    url = f"{BASE_URL}/planner/plans/{plan_id}"
    current_headers = headers.copy(); body_data = nuevos_valores.copy()
    final_etag = etag or body_data.pop('@odata.etag', None)
    if final_etag: current_headers['If-Match'] = final_etag; logger.info(f"Usando ETag '{final_etag}' para actualizar plan {plan_id}")
    else: logger.warning(f"Actualizando plan {plan_id} sin ETag.")

    logger.info(f"Actualizando plan de Planner '{plan_id}'")
    try:
        result = hacer_llamada_api("PATCH", url, current_headers, json_data=body_data, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        if result is None:
            return {"status": "success", "message": f"Plan '{plan_id}' actualizado (204 No Content)."}
        return {"status": "success", "data": result, "message": f"Plan '{plan_id}' actualizado."}
    except Exception as e:
        logger.error(f"Error actualizando plan Planner '{plan_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al actualizar plan: {type(e).__name__}", "http_status": status_code, "details": details}

def eliminar_plan(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    plan_id: Optional[str] = parametros.get("plan_id")
    etag: Optional[str] = parametros.get("etag")
    if not plan_id: return {"status": "error", "message": "Parámetro 'plan_id' es requerido."}

    url = f"{BASE_URL}/planner/plans/{plan_id}"
    current_headers = headers.copy()
    if etag: current_headers['If-Match'] = etag; logger.info(f"Eliminando plan {plan_id} con ETag '{etag}'.")
    else: logger.warning(f"Eliminando plan {plan_id} sin ETag.")
    
    logger.info(f"Eliminando plan de Planner '{plan_id}'")
    try:
        hacer_llamada_api("DELETE", url, current_headers, timeout=GRAPH_API_DEFAULT_TIMEOUT, expect_json=False)
        return {"status": "success", "message": f"Plan '{plan_id}' eliminado."}
    except Exception as e:
        logger.error(f"Error eliminando plan Planner '{plan_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al eliminar plan: {type(e).__name__}", "http_status": status_code, "details": details}

def listar_tareas_planner(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    plan_id: Optional[str] = parametros.get("plan_id")
    top_per_page: int = min(int(parametros.get('top_per_page', 25)), 100)
    max_items_total: int = int(parametros.get('max_items_total', 100))
    select: Optional[str] = parametros.get('select') # ej: "id,title,percentComplete,dueDateTime"
    filter_query: Optional[str] = parametros.get('filter_query')
    order_by: Optional[str] = parametros.get('order_by')
    if not plan_id: return {"status": "error", "message": "Parámetro 'plan_id' es requerido."}

    url_base = f"{BASE_URL}/planner/plans/{plan_id}/tasks"
    query_params: Dict[str, Any] = {'$top': top_per_page}
    if select: query_params['$select'] = select
    if filter_query: query_params['$filter'] = filter_query
    if order_by: query_params['$orderby'] = order_by
    
    all_tasks: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0
    logger.info(f"Listando tareas Planner plan '{plan_id}' (max: {max_items_total}, pág: {top_per_page})")
    try:
        while current_url and len(all_tasks) < max_items_total:
            page_count += 1
            params_for_call = query_params if current_url == url_base and page_count == 1 else None
            logger.debug(f" Obteniendo página {page_count} de tareas Planner desde: {current_url}")
            response_data = hacer_llamada_api("GET", current_url, headers, params=params_for_call, timeout=GRAPH_API_DEFAULT_TIMEOUT)
            if response_data and isinstance(response_data, dict) and 'value' in response_data:
                items_in_page = response_data.get('value', [])
                if not isinstance(items_in_page, list): break
                for item in items_in_page:
                    if len(all_tasks) < max_items_total: all_tasks.append(item)
                    else: break
                current_url = response_data.get('@odata.nextLink')
                if not current_url or len(all_tasks) >= max_items_total: break
            else: break
        logger.info(f"Total tareas Planner recuperadas: {len(all_tasks)} ({page_count} pág).")
        return {"status": "success", "data": all_tasks, "total_retrieved": len(all_tasks), "pages_processed": page_count}
    except Exception as e:
        logger.error(f"Error listando tareas Planner: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al listar tareas Planner: {type(e).__name__}", "http_status": status_code, "details": details}

def crear_tarea_planner(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    plan_id: Optional[str] = parametros.get("plan_id")
    titulo_tarea: Optional[str] = parametros.get("titulo_tarea")
    bucket_id: Optional[str] = parametros.get("bucket_id")
    # Ejemplo 'assignments': {"USER_ID1": {"@odata.type": "#microsoft.graph.plannerAssignment", "orderHint": " !"}, "USER_ID2": ...}
    assignments: Optional[Dict[str, Any]] = parametros.get("assignments")
    due_datetime_str: Optional[str] = parametros.get("dueDateTime") # ISO 8601 string
    # Más campos: percentComplete, priority, checklistItems, etc.
    # 'details' puede contener descripción, checklist, referencias.
    details_payload: Optional[Dict[str, Any]] = parametros.get("details_payload")


    if not plan_id or not titulo_tarea:
        return {"status": "error", "message": "Parámetros 'plan_id' y 'titulo_tarea' son requeridos."}

    url = f"{BASE_URL}/planner/tasks"
    body: Dict[str, Any] = {"planId": plan_id, "title": titulo_tarea}
    if bucket_id: body["bucketId"] = bucket_id
    if assignments and isinstance(assignments, dict): body["assignments"] = assignments
    if due_datetime_str:
        try: body["dueDateTime"] = _parse_and_utc_datetime_str(due_datetime_str, "dueDateTime")
        except ValueError as ve: return {"status": "error", "message": f"Formato inválido para 'dueDateTime': {ve}"}
    
    # Si se provee details_payload, se usa para actualizar los detalles después de crear la tarea base.
    # La creación de tareas con detalles complejos a veces es mejor en dos pasos.
    
    logger.info(f"Creando tarea Planner '{titulo_tarea}' en plan '{plan_id}'")
    try:
        task_data = hacer_llamada_api("POST", url, headers, json_data=body, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        
        # Si hay details_payload y la tarea se creó, actualizar detalles
        if details_payload and isinstance(details_payload, dict) and task_data and task_data.get("id"):
            task_id = task_data.get("id")
            etag_details = task_data.get("details", {}).get("@odata.etag") # Planner task details has its own etag
            logger.info(f"Tarea Planner '{task_id}' creada, actualizando detalles...")
            details_url = f"{BASE_URL}/planner/tasks/{task_id}/details"
            details_headers = headers.copy()
            if etag_details: details_headers['If-Match'] = etag_details
            
            hacer_llamada_api("PATCH", details_url, details_headers, json_data=details_payload, timeout=GRAPH_API_DEFAULT_TIMEOUT)
            logger.info(f"Detalles de tarea Planner '{task_id}' actualizados.")
            # Re-obtener la tarea con detalles actualizados podría ser útil, o simplemente devolver la tarea base.
            # Por simplicidad, devolvemos la tarea base y un mensaje sobre los detalles.
            task_data["details_updated_separately"] = True

        return {"status": "success", "data": task_data, "message": "Tarea Planner creada (y detalles actualizados si se proveyeron)."}
    except Exception as e:
        logger.error(f"Error creando tarea Planner: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al crear tarea Planner: {type(e).__name__}", "http_status": status_code, "details": details}

def actualizar_tarea_planner(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    tarea_id: Optional[str] = parametros.get("tarea_id")
    nuevos_valores: Optional[Dict[str, Any]] = parametros.get("nuevos_valores")
    etag: Optional[str] = parametros.get("etag") # ETag de la tarea principal
    # Si se actualizan detalles, se necesita el ETag de los detalles:
    # nuevos_valores podría contener un sub-diccionario "details" con su propio "@odata.etag"

    if not tarea_id or not nuevos_valores or not isinstance(nuevos_valores, dict):
        return {"status": "error", "message": "Params 'tarea_id' y 'nuevos_valores' (dict) requeridos."}

    current_headers = headers.copy()
    body_data = nuevos_valores.copy()
    final_etag = etag or body_data.pop('@odata.etag', None)
    if final_etag: current_headers['If-Match'] = final_etag; logger.info(f"Usando ETag '{final_etag}' para tarea Planner {tarea_id}")
    else: logger.warning(f"Actualizando tarea Planner {tarea_id} sin ETag principal.")
    
    # Separar actualización de detalles si viene en nuevos_valores
    details_payload = body_data.pop("details", None)

    updated_task_data = None
    if body_data: # Si hay campos para actualizar en la tarea principal
        url_task = f"{BASE_URL}/planner/tasks/{tarea_id}"
        logger.info(f"Actualizando tarea Planner '{tarea_id}' (campos principales)")
        try:
            updated_task_data = hacer_llamada_api("PATCH", url_task, current_headers, json_data=body_data, timeout=GRAPH_API_DEFAULT_TIMEOUT)
            if updated_task_data is None: # 204
                 # Re-obtener la tarea si fue 204 y necesitamos devolverla. Por ahora, mensaje.
                 logger.info(f"Tarea Planner '{tarea_id}' actualizada (204 No Content).")
                 updated_task_data = {"id": tarea_id, "message": "Actualización principal completada (204)."}
        except Exception as e:
            logger.error(f"Error actualizando campos principales de tarea Planner '{tarea_id}': {type(e).__name__} - {e}", exc_info=True)
            details = str(e); status_code=500
            if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                status_code = e.response.status_code; try: details = e.response.json()
                except json.JSONDecodeError: details = e.response.text
            return {"status": "error", "message": f"Error al actualizar tarea Planner: {type(e).__name__}", "http_status": status_code, "details": details}

    if details_payload and isinstance(details_payload, dict):
        logger.info(f"Actualizando detalles para tarea Planner '{tarea_id}'")
        url_details = f"{BASE_URL}/planner/tasks/{tarea_id}/details"
        details_headers = headers.copy() # Usar headers originales para la sub-petición
        etag_details = details_payload.pop('@odata.etag', None) # ETag específico de detalles
        if etag_details: details_headers['If-Match'] = etag_details
        else: logger.warning(f"Actualizando detalles de tarea {tarea_id} sin ETag de detalles.")
        try:
            hacer_llamada_api("PATCH", url_details, details_headers, json_data=details_payload, timeout=GRAPH_API_DEFAULT_TIMEOUT)
            logger.info(f"Detalles de tarea Planner '{tarea_id}' actualizados.")
            if updated_task_data and isinstance(updated_task_data, dict): # Si ya teníamos datos de la tarea
                updated_task_data["details_message"] = "Detalles actualizados."
            else: # Si solo se actualizaron detalles
                updated_task_data = {"id": tarea_id, "message": "Solo detalles actualizados."}
        except Exception as e_details:
            logger.error(f"Error actualizando detalles de tarea Planner '{tarea_id}': {type(e_details).__name__} - {e_details}", exc_info=True)
            # No fallar toda la operación si solo fallan los detalles, pero informar
            if updated_task_data and isinstance(updated_task_data, dict):
                updated_task_data["details_error"] = str(e_details)
            else:
                return {"status": "error", "message": f"Error al actualizar detalles de tarea: {type(e_details).__name__}", "details": str(e_details)}
    
    if updated_task_data:
        return {"status": "success", "data": updated_task_data, "message": "Tarea Planner actualizada."}
    else: # Si no se actualizó nada (ej. body_data y details_payload estaban vacíos)
        return {"status": "success", "message": "No se especificaron cambios para la tarea Planner.", "id": tarea_id}

def eliminar_tarea_planner(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    tarea_id: Optional[str] = parametros.get("tarea_id")
    etag: Optional[str] = parametros.get("etag")
    if not tarea_id: return {"status": "error", "message": "Parámetro 'tarea_id' es requerido."}

    url = f"{BASE_URL}/planner/tasks/{tarea_id}"
    current_headers = headers.copy()
    if etag: current_headers['If-Match'] = etag; logger.info(f"Eliminando tarea Planner {tarea_id} con ETag.")
    else: logger.warning(f"Eliminando tarea Planner {tarea_id} sin ETag.")
    
    logger.info(f"Eliminando tarea Planner '{tarea_id}'")
    try:
        hacer_llamada_api("DELETE", url, current_headers, timeout=GRAPH_API_DEFAULT_TIMEOUT, expect_json=False)
        return {"status": "success", "message": f"Tarea Planner '{tarea_id}' eliminada."}
    except Exception as e:
        logger.error(f"Error eliminando tarea Planner '{tarea_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al eliminar tarea Planner: {type(e).__name__}", "http_status": status_code, "details": details}

# =================================
# ==== FUNCIONES ACCIÓN TO-DO ====
# =================================
# Requieren permisos como Tasks.ReadWrite, Tasks.Read

def listar_listas_todo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    url_base = f"{BASE_URL}/me/todo/lists"
    top_per_page: int = min(int(parametros.get('top_per_page', 25)), 100)
    max_items_total: int = int(parametros.get('max_items_total', 100))
    select: Optional[str] = parametros.get('select')
    filter_query: Optional[str] = parametros.get('filter_query')
    order_by: Optional[str] = parametros.get('order_by')

    query_params: Dict[str, Any] = {'$top': top_per_page}
    if select: query_params['$select'] = select
    if filter_query: query_params['$filter'] = filter_query
    if order_by: query_params['$orderby'] = order_by

    all_lists: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0
    logger.info(f"Listando listas de ToDo para /me (max: {max_items_total}, pág: {top_per_page})")
    try:
        while current_url and len(all_lists) < max_items_total:
            page_count += 1
            params_for_call = query_params if current_url == url_base and page_count == 1 else None
            logger.debug(f" Obteniendo página {page_count} de listas ToDo desde: {current_url}")
            response_data = hacer_llamada_api("GET", current_url, headers, params=params_for_call, timeout=GRAPH_API_DEFAULT_TIMEOUT)
            if response_data and isinstance(response_data, dict) and 'value' in response_data:
                items_in_page = response_data.get('value', [])
                if not isinstance(items_in_page, list): break
                for item in items_in_page:
                    if len(all_lists) < max_items_total: all_lists.append(item)
                    else: break
                current_url = response_data.get('@odata.nextLink')
                if not current_url or len(all_lists) >= max_items_total: break
            else: break
        logger.info(f"Total listas ToDo recuperadas: {len(all_lists)} ({page_count} pág).")
        return {"status": "success", "data": all_lists, "total_retrieved": len(all_lists), "pages_processed": page_count}
    except Exception as e:
        logger.error(f"Error listando listas ToDo: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al listar listas ToDo: {type(e).__name__}", "http_status": status_code, "details": details}

def crear_lista_todo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    nombre_lista: Optional[str] = parametros.get("nombre_lista")
    if not nombre_lista: return {"status": "error", "message": "Parámetro 'nombre_lista' es requerido."}
    url = f"{BASE_URL}/me/todo/lists"
    body = {"displayName": nombre_lista}
    logger.info(f"Creando lista de ToDo '{nombre_lista}' para /me")
    try:
        list_data = hacer_llamada_api("POST", url, headers, json_data=body, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": list_data, "message": "Lista ToDo creada."}
    except Exception as e:
        logger.error(f"Error creando lista ToDo: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al crear lista ToDo: {type(e).__name__}", "http_status": status_code, "details": details}

def actualizar_lista_todo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    lista_id: Optional[str] = parametros.get("lista_id")
    nuevos_valores: Optional[Dict[str, Any]] = parametros.get("nuevos_valores")
    if not lista_id or not nuevos_valores or not isinstance(nuevos_valores, dict):
        return {"status": "error", "message": "Params 'lista_id' y 'nuevos_valores' (dict) requeridos."}
    url = f"{BASE_URL}/me/todo/lists/{lista_id}"
    logger.info(f"Actualizando lista de ToDo '{lista_id}'")
    try:
        # PATCH puede devolver 200 con cuerpo o 204 sin cuerpo
        updated_list = hacer_llamada_api("PATCH", url, headers, json_data=nuevos_valores, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        if updated_list is None: # 204
            return {"status": "success", "message": f"Lista ToDo '{lista_id}' actualizada (204)."}
        return {"status": "success", "data": updated_list, "message": f"Lista ToDo '{lista_id}' actualizada."}
    except Exception as e:
        logger.error(f"Error actualizando lista ToDo '{lista_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al actualizar lista ToDo: {type(e).__name__}", "http_status": status_code, "details": details}

def eliminar_lista_todo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    lista_id: Optional[str] = parametros.get("lista_id")
    if not lista_id: return {"status": "error", "message": "Parámetro 'lista_id' es requerido."}
    url = f"{BASE_URL}/me/todo/lists/{lista_id}"
    logger.info(f"Eliminando lista de ToDo '{lista_id}'")
    try:
        hacer_llamada_api("DELETE", url, headers, timeout=GRAPH_API_DEFAULT_TIMEOUT, expect_json=False)
        return {"status": "success", "message": f"Lista ToDo '{lista_id}' eliminada."}
    except Exception as e:
        logger.error(f"Error eliminando lista ToDo '{lista_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al eliminar lista ToDo: {type(e).__name__}", "http_status": status_code, "details": details}

def listar_tareas_todo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    lista_id: Optional[str] = parametros.get("lista_id")
    top_per_page: int = min(int(parametros.get('top_per_page', 25)), 100) # Max 100 para ToDo Tasks
    max_items_total: int = int(parametros.get('max_items_total', 100))
    select: Optional[str] = parametros.get('select')
    filter_query: Optional[str] = parametros.get('filter_query') # Ej: "status ne 'completed'"
    order_by: Optional[str] = parametros.get('order_by')
    if not lista_id: return {"status": "error", "message": "Parámetro 'lista_id' es requerido."}

    url_base = f"{BASE_URL}/me/todo/lists/{lista_id}/tasks"
    query_params: Dict[str, Any] = {'$top': top_per_page}
    if select: query_params['$select'] = select
    if filter_query: query_params['$filter'] = filter_query
    if order_by: query_params['$orderby'] = order_by
    
    all_tasks: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0
    logger.info(f"Listando tareas ToDo lista '{lista_id}' (max: {max_items_total}, pág: {top_per_page})")
    try:
        while current_url and len(all_tasks) < max_items_total:
            page_count += 1
            params_for_call = query_params if current_url == url_base and page_count == 1 else None
            logger.debug(f" Obteniendo página {page_count} de tareas ToDo desde: {current_url}")
            response_data = hacer_llamada_api("GET", current_url, headers, params=params_for_call, timeout=GRAPH_API_DEFAULT_TIMEOUT)
            if response_data and isinstance(response_data, dict) and 'value' in response_data:
                items_in_page = response_data.get('value', [])
                if not isinstance(items_in_page, list): break
                for item in items_in_page:
                    if len(all_tasks) < max_items_total: all_tasks.append(item)
                    else: break
                current_url = response_data.get('@odata.nextLink')
                if not current_url or len(all_tasks) >= max_items_total: break
            else: break
        logger.info(f"Total tareas ToDo recuperadas: {len(all_tasks)} ({page_count} pág).")
        return {"status": "success", "data": all_tasks, "total_retrieved": len(all_tasks), "pages_processed": page_count}
    except Exception as e:
        logger.error(f"Error listando tareas ToDo: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al listar tareas ToDo: {type(e).__name__}", "http_status": status_code, "details": details}

def crear_tarea_todo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    lista_id: Optional[str] = parametros.get("lista_id")
    titulo_tarea: Optional[str] = parametros.get("titulo_tarea")
    if not lista_id or not titulo_tarea:
        return {"status": "error", "message": "Params 'lista_id' y 'titulo_tarea' requeridos."}

    url = f"{BASE_URL}/me/todo/lists/{lista_id}/tasks"
    body: Dict[str, Any] = {"title": titulo_tarea}
    # Añadir más campos opcionales al body desde 'parametros' según la API de Graph para todoTask
    if "body_content" in parametros and "body_contentType" in parametros:
        body["body"] = {"content": parametros["body_content"], "contentType": parametros["body_contentType"]}
    if "importance" in parametros: body["importance"] = parametros["importance"] # low, normal, high
    if "isReminderOn" in parametros: body["isReminderOn"] = bool(parametros["isReminderOn"])
    if "dueDateTime" in parametros: # Espera dict: {"dateTime": "YYYY-MM-DDTHH:MM:SS", "timeZone": "UTC"}
        try:
            due_dt_str = _parse_and_utc_datetime_str(parametros["dueDateTime"].get("dateTime") if isinstance(parametros["dueDateTime"],dict) else parametros["dueDateTime"], "dueDateTime")
            body["dueDateTime"] = {"dateTime": due_dt_str, "timeZone": "UTC"}
        except (ValueError, AttributeError) as ve: return {"status": "error", "message": f"Formato inválido para 'dueDateTime': {ve}"}

    logger.info(f"Creando tarea ToDo '{titulo_tarea}' en lista '{lista_id}'")
    try:
        task_data = hacer_llamada_api("POST", url, headers, json_data=body, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": task_data, "message": "Tarea ToDo creada."}
    except Exception as e:
        logger.error(f"Error creando tarea ToDo: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al crear tarea ToDo: {type(e).__name__}", "http_status": status_code, "details": details}

def actualizar_tarea_todo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    lista_id: Optional[str] = parametros.get("lista_id")
    tarea_id: Optional[str] = parametros.get("tarea_id")
    nuevos_valores: Optional[Dict[str, Any]] = parametros.get("nuevos_valores")
    if not lista_id or not tarea_id or not nuevos_valores or not isinstance(nuevos_valores, dict):
        return {"status": "error", "message": "Params 'lista_id', 'tarea_id', 'nuevos_valores' (dict) requeridos."}

    url = f"{BASE_URL}/me/todo/lists/{lista_id}/tasks/{tarea_id}"
    body_update = nuevos_valores.copy()
    # Normalizar fechas si vienen en el payload de actualización
    try:
        if "dueDateTime" in body_update and body_update["dueDateTime"]:
            due_dt_val = body_update["dueDateTime"].get("dateTime") if isinstance(body_update["dueDateTime"],dict) else body_update["dueDateTime"]
            due_dt_str = _parse_and_utc_datetime_str(due_dt_val, "nuevos_valores.dueDateTime")
            body_update["dueDateTime"] = {"dateTime": due_dt_str, "timeZone": "UTC"}
        if "reminderDateTime" in body_update and body_update["reminderDateTime"]:
            rem_dt_val = body_update["reminderDateTime"].get("dateTime") if isinstance(body_update["reminderDateTime"],dict) else body_update["reminderDateTime"]
            rem_dt_str = _parse_and_utc_datetime_str(rem_dt_val, "nuevos_valores.reminderDateTime")
            body_update["reminderDateTime"] = {"dateTime": rem_dt_str, "timeZone": "UTC"}
    except ValueError as ve: return {"status": "error", "message": str(ve)}
        
    logger.info(f"Actualizando tarea ToDo '{tarea_id}' en lista '{lista_id}'")
    try:
        updated_task = hacer_llamada_api("PATCH", url, headers, json_data=body_update, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        if updated_task is None: # 204 No Content
            return {"status": "success", "message": f"Tarea ToDo '{tarea_id}' actualizada (204)."}
        return {"status": "success", "data": updated_task, "message": f"Tarea ToDo '{tarea_id}' actualizada."}
    except Exception as e:
        logger.error(f"Error actualizando tarea ToDo '{tarea_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al actualizar tarea ToDo: {type(e).__name__}", "http_status": status_code, "details": details}

def eliminar_tarea_todo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    lista_id: Optional[str] = parametros.get("lista_id")
    tarea_id: Optional[str] = parametros.get("tarea_id")
    if not lista_id or not tarea_id:
        return {"status": "error", "message": "Params 'lista_id' y 'tarea_id' requeridos."}

    url = f"{BASE_URL}/me/todo/lists/{lista_id}/tasks/{tarea_id}"
    logger.info(f"Eliminando tarea ToDo '{tarea_id}' de lista '{lista_id}'")
    try:
        hacer_llamada_api("DELETE", url, headers, timeout=GRAPH_API_DEFAULT_TIMEOUT, expect_json=False)
        return {"status": "success", "message": f"Tarea ToDo '{tarea_id}' eliminada."}
    except Exception as e:
        logger.error(f"Error eliminando tarea ToDo '{tarea_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al eliminar tarea ToDo: {type(e).__name__}", "http_status": status_code, "details": details}

def completar_tarea_todo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    lista_id: Optional[str] = parametros.get("lista_id")
    tarea_id: Optional[str] = parametros.get("tarea_id")
    if not lista_id or not tarea_id:
        return {"status": "error", "message": "Params 'lista_id' y 'tarea_id' requeridos."}
    
    logger.info(f"Marcando tarea ToDo '{tarea_id}' en lista '{lista_id}' como completada.")
    # Para completar, se actualiza el estado a 'completed' y se establece completedDateTime
    payload = {
        "status": "completed",
        "completedDateTime": {
            "dateTime": datetime.now(dt_timezone.utc).isoformat(timespec='seconds') + "Z",
            "timeZone": "UTC"
        }
    }
    params_actualizar = {"lista_id": lista_id, "tarea_id": tarea_id, "nuevos_valores": payload}
    return actualizar_tarea_todo(params_actualizar, headers)

# --- FIN DEL MÓDULO actions/planner_todo_actions.py ---