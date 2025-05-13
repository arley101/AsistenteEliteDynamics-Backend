# MyHttpTrigger/actions/calendario_actions.py
import logging
import requests # Solo para tipos de excepción y la clase HTTPError
import json
from typing import Dict, List, Optional, Any

# Importar el cliente autenticado y las constantes
from ..shared.helpers.http_client import AuthenticatedHttpClient
from ..shared import constants # GRAPH_API_BASE_URL, GRAPH_SCOPE, etc.

logger = logging.getLogger(__name__)

# --- Helper para manejar errores de Calendar API de forma centralizada ---
def _handle_calendar_api_error(e: Exception, action_name: str, params_for_log: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    log_message = f"Error en Calendar action '{action_name}'"
    if params_for_log:
        safe_params = {k: v for k, v in params_for_log.items() if k not in ['body', 'event_payload', 'event_body_update', 'meeting_params_body', 'schedule_params_body', 'attendees']}
        log_message += f" con params: {safe_params}"
    log_message += f": {type(e).__name__} - {e}"
    
    logger.error(log_message, exc_info=True)
    
    details = str(e)
    status_code = 500
    error_code_graph = None

    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
        status_code = e.response.status_code
        try:
            error_data = e.response.json()
            details = error_data.get("error", {}).get("message", e.response.text)
            error_code_graph = error_data.get("error", {}).get("code")
        except json.JSONDecodeError:
            details = e.response.text
            
    return {
        "status": "error",
        "action": action_name,
        "message": f"Error en {action_name}: {type(e).__name__}",
        "http_status": status_code,
        "details": details,
        "graph_error_code": error_code_graph
    }

# --- Helper común para paginación ---
def _calendar_paged_request(
    client: AuthenticatedHttpClient,
    url_base: str,
    scope: str,
    params: Dict[str, Any], 
    query_api_params_initial: Dict[str, Any],
    max_items_total: int,
    action_name_for_log: str
) -> Dict[str, Any]:
    all_items: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0
    max_pages = 20 
    
    top_per_page = query_api_params_initial.get('$top', 50)

    logger.info(f"Iniciando solicitud paginada para '{action_name_for_log}' desde '{url_base.split('?')[0]}...'. "
                f"Max total: {max_items_total}, por página: {top_per_page}, max_páginas: {max_pages}")
    try:
        while current_url and len(all_items) < max_items_total and page_count < max_pages:
            page_count += 1
            is_first_call = (current_url == url_base and page_count == 1)
            
            logger.debug(f"Página {page_count} para '{action_name_for_log}': GET {current_url.split('?')[0]}...")
            response = client.get(
                url=current_url, 
                scope=scope, 
                params=query_api_params_initial if is_first_call else None
            )
            response_data = response.json()
            
            page_items = response_data.get('value', [])
            if not isinstance(page_items, list):
                logger.warning(f"Respuesta inesperada, 'value' no es una lista: {response_data}")
                break
            
            for item in page_items:
                if len(all_items) < max_items_total:
                    all_items.append(item)
                else:
                    break 
            
            current_url = response_data.get('@odata.nextLink')
            if not current_url or len(all_items) >= max_items_total:
                break 
        
        logger.info(f"'{action_name_for_log}' recuperó {len(all_items)} items en {page_count} páginas.")
        return {"status": "success", "data": all_items, "total_retrieved": len(all_items), "pages_processed": page_count}
    except Exception as e:
        return _handle_calendar_api_error(e, action_name_for_log, params)

# ---- FUNCIONES DE ACCIÓN PARA CALENDARIO ----
# Nombres de función ajustados para coincidir EXACTAMENTE con lo esperado por mapping_actions.py

def calendar_list_events(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Nombre esperado por mapping
    start_datetime_str: Optional[str] = params.get('start_datetime')
    end_datetime_str: Optional[str] = params.get('end_datetime')
    top_per_page: int = min(int(params.get('top_per_page', 25)), 100)
    max_items_total: int = int(params.get('max_items_total', 100))
    select: Optional[str] = params.get('select')
    filter_query: Optional[str] = params.get('filter')
    order_by: Optional[str] = params.get('orderby', 'start/dateTime')

    query_api_params: Dict[str, Any] = {'$top': top_per_page}
    if select: query_api_params['$select'] = select
    if order_by: query_api_params['$orderby'] = order_by

    if start_datetime_str and end_datetime_str:
        query_api_params['startDateTime'] = start_datetime_str
        query_api_params['endDateTime'] = end_datetime_str
        url_base = f"{constants.GRAPH_API_BASE_URL}/me/calendarView"
        log_action = f"calendar_list_events (/calendarView entre {start_datetime_str} y {end_datetime_str})"
    else:
        url_base = f"{constants.GRAPH_API_BASE_URL}/me/events"
        log_action = "calendar_list_events (/events)"
        if filter_query: query_api_params['$filter'] = filter_query
    
    return _calendar_paged_request(client, url_base, constants.GRAPH_SCOPE_CALENDARS_READ, params, query_api_params, max_items_total, log_action)

def calendar_create_event(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Nombre esperado por mapping
    event_payload: Optional[Dict[str, Any]] = params.get("event_payload", params) 

    required_fields = ["subject", "start", "end"]
    if not all(field in event_payload for field in required_fields):
        return _handle_calendar_api_error(ValueError("Faltan campos requeridos (subject, start, end)."), "calendar_create_event", params)
    
    for field_name in ["start", "end"]:
        if not isinstance(event_payload.get(field_name), dict) or \
           not event_payload[field_name].get("dateTime") or \
           not event_payload[field_name].get("timeZone"):
            return _handle_calendar_api_error(ValueError(f"Campo '{field_name}' malformado."), "calendar_create_event", params)

    url = f"{constants.GRAPH_API_BASE_URL}/me/events"
    logger.info(f"Creando evento. Asunto: {event_payload.get('subject')}")
    try:
        response = client.post(url, scope=constants.GRAPH_SCOPE_CALENDARS_READ_WRITE, json=event_payload)
        created_event = response.json()
        logger.info(f"Evento '{event_payload.get('subject')}' creado. ID: {created_event.get('id')}")
        return {"status": "success", "data": created_event}
    except Exception as e:
        return _handle_calendar_api_error(e, "calendar_create_event", params)

def get_event(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Nombre esperado por mapping
    event_id: Optional[str] = params.get("event_id")
    select: Optional[str] = params.get("select")
    if not event_id:
        return _handle_calendar_api_error(ValueError("'event_id' es requerido."), "get_event", params)
    
    url = f"{constants.GRAPH_API_BASE_URL}/me/events/{event_id}"
    query_api_params = {'$select': select} if select else None
    logger.info(f"Obteniendo evento ID: {event_id} (Select: {select or 'default'})")
    try:
        response = client.get(url, scope=constants.GRAPH_SCOPE_CALENDARS_READ, params=query_api_params)
        return {"status": "success", "data": response.json()}
    except Exception as e:
        return _handle_calendar_api_error(e, "get_event", params)

def update_event(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Nombre esperado por mapping
    event_id: Optional[str] = params.get("event_id")
    update_payload: Optional[Dict[str, Any]] = params.get("update_payload", {k:v for k,v in params.items() if k not in ["action", "event_id", "target_service"]})

    if not event_id:
        return _handle_calendar_api_error(ValueError("'event_id' es requerido."), "update_event", params)
    if not update_payload or not isinstance(update_payload, dict) or not update_payload:
        return _handle_calendar_api_error(ValueError("'update_payload' (dict con campos) es requerido."), "update_event", params)

    for field_name in ["start", "end"]:
        if field_name in update_payload:
            field_value = update_payload[field_name]
            if not isinstance(field_value, dict) or \
               not field_value.get("dateTime") or \
               not field_value.get("timeZone"):
                return _handle_calendar_api_error(ValueError(f"Si actualiza '{field_name}', debe ser dict con 'dateTime' y 'timeZone'."), "update_event", params)

    url = f"{constants.GRAPH_API_BASE_URL}/me/events/{event_id}"
    logger.info(f"Actualizando evento ID: {event_id}")
    try:
        response = client.patch(url, scope=constants.GRAPH_SCOPE_CALENDARS_READ_WRITE, json=update_payload)
        return {"status": "success", "data": response.json()}
    except Exception as e:
        return _handle_calendar_api_error(e, "update_event", params)

def delete_event(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Nombre esperado por mapping
    event_id: Optional[str] = params.get("event_id")
    if not event_id:
        return _handle_calendar_api_error(ValueError("'event_id' es requerido."), "delete_event", params)

    url = f"{constants.GRAPH_API_BASE_URL}/me/events/{event_id}"
    logger.info(f"Eliminando evento ID: {event_id}")
    try:
        response = client.delete(url, scope=constants.GRAPH_SCOPE_CALENDARS_READ_WRITE)
        return {"status": "success", "message": f"Evento '{event_id}' eliminado.", "http_status": response.status_code}
    except Exception as e:
        return _handle_calendar_api_error(e, "delete_event", params)

def find_meeting_times(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Nombre esperado por mapping
    meeting_params_body: Optional[Dict[str, Any]] = params.get("meeting_params_body", params)
    
    if not isinstance(meeting_params_body, dict) or \
       not meeting_params_body.get("timeConstraint") or \
       not isinstance(meeting_params_body.get("attendees", []), list):
        return _handle_calendar_api_error(ValueError("Parámetro 'meeting_params_body' es requerido con 'timeConstraint'."), "find_meeting_times", params)

    url = f"{constants.GRAPH_API_BASE_URL}/me/findMeetingTimes"
    logger.info("Buscando horarios de reunión (findMeetingTimes).")
    try:
        response = client.post(url, scope=constants.GRAPH_SCOPE_CALENDARS_READ, json=meeting_params_body)
        return {"status": "success", "data": response.json()}
    except Exception as e:
        return _handle_calendar_api_error(e, "find_meeting_times", params)

def get_schedule(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]: # Nombre esperado por mapping
    schedule_params_body: Optional[Dict[str, Any]] = params.get("schedule_params_body", params)

    if not isinstance(schedule_params_body, dict) or \
       not schedule_params_body.get("schedules") or \
       not schedule_params_body.get("startTime") or \
       not schedule_params_body.get("endTime"):
        return _handle_calendar_api_error(ValueError("Parámetro 'schedule_params_body' es requerido con 'schedules', 'startTime', 'endTime'."), "get_schedule", params)

    url = f"{constants.GRAPH_API_BASE_URL}/me/calendar/getSchedule"
    logger.info("Obteniendo información de calendario (getSchedule).")
    try:
        response = client.post(url, scope=constants.GRAPH_SCOPE_CALENDARS_READ_SHARED, json=schedule_params_body)
        return {"status": "success", "data": response.json()}
    except Exception as e:
        return _handle_calendar_api_error(e, "get_schedule", params)

# --- FIN DEL MÓDULO actions/calendario_actions.py ---