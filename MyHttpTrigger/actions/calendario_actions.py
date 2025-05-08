# MyHttpTrigger/actions/calendario_actions.py
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
    logging.critical(f"Error CRÍTICO importando dependencias compartidas en Calendario: {e}.", exc_info=True)
    BASE_URL = "https://graph.microsoft.com/v1.0"
    GRAPH_API_DEFAULT_TIMEOUT = 45
    APP_NAME = "EliteDynamicsPro" # Fallback
    raise ImportError(f"No se pudo importar 'hacer_llamada_api' o constantes: {e}") from e

logger = logging.getLogger(f"{APP_NAME}.actions.calendario")

# ---- Helper Interno para Parseo y Normalización de Fechas/Horas a UTC ----
def _parse_and_utc_datetime_str(datetime_str: Optional[str], param_name: str) -> Optional[str]:
    """
    Parsea un string de fecha/hora ISO y lo devuelve como string ISO en UTC (formato Z).
    Lanza ValueError si el formato es inválido o si datetime_str es None y es requerido.
    """
    if not datetime_str:
        return None

    try:
        # Intentar parsear con y sin 'Z', manejando posibles offsets
        if isinstance(datetime_str, datetime): # Si ya es datetime, usarlo
             dt_obj = datetime_str
        elif isinstance(datetime_str, str):
             if datetime_str.endswith('Z'):
                 dt_obj = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
             else:
                 dt_obj = datetime.fromisoformat(datetime_str)
        else:
            raise TypeError(f"Tipo inesperado para fecha/hora: {type(datetime_str)}")

        # Si es naive, asumir UTC. Si tiene timezone, convertir a UTC.
        if dt_obj.tzinfo is None or dt_obj.tzinfo.utcoffset(dt_obj) is None:
            dt_obj_utc = dt_obj.replace(tzinfo=dt_timezone.utc)
        else:
            dt_obj_utc = dt_obj.astimezone(dt_timezone.utc)
        
        # Devolver en formato ISO con Z para UTC
        return dt_obj_utc.isoformat(timespec='seconds').replace('+00:00', 'Z')
    except (ValueError, TypeError) as ve:
        logger.error(f"Error parseando '{param_name}': '{datetime_str}' no es un formato ISO 8601 válido o tipo incorrecto. {ve}")
        raise ValueError(f"Parámetro '{param_name}' debe ser un string en formato ISO 8601 (ej: 2025-MM-DDTHH:MM:SSZ) o un objeto datetime.") from ve

# ---- FUNCIONES DE ACCIÓN PARA CALENDARIO ----

def listar_eventos(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    mailbox: str = parametros.get('mailbox', 'me')
    start_datetime_str: Optional[str] = parametros.get('start_datetime')
    end_datetime_str: Optional[str] = parametros.get('end_datetime')
    timezone_display: str = parametros.get('timezone_display', 'UTC')
    top_per_page: int = min(int(parametros.get('top_per_page', 25)), 50)
    max_items_total: int = int(parametros.get('max_items_total', 100))
    select: Optional[str] = parametros.get('select')
    filter_query: Optional[str] = parametros.get('filter_query')
    order_by: Optional[str] = parametros.get('order_by', 'start/dateTime asc')

    if not start_datetime_str or not end_datetime_str:
        return {"status": "error", "message": "Parámetros 'start_datetime' y 'end_datetime' son requeridos."}

    try:
        start_utc_str = _parse_and_utc_datetime_str(start_datetime_str, "start_datetime")
        end_utc_str = _parse_and_utc_datetime_str(end_datetime_str, "end_datetime")
        if not start_utc_str or not end_utc_str : raise ValueError("Fechas inválidas.")
    except ValueError as ve: return {"status": "error", "message": str(ve)}

    url_base = f"{BASE_URL}/users/{mailbox}/calendarView"
    query_params: Dict[str, Any] = {'startDateTime': start_utc_str, 'endDateTime': end_utc_str, '$top': top_per_page}
    if select: query_params['$select'] = select
    if filter_query: query_params['$filter'] = filter_query
    if order_by: query_params['$orderby'] = order_by
    
    request_headers = headers.copy(); request_headers['Prefer'] = f'outlook.timezone="{timezone_display}"'
    all_events: List[Dict[str, Any]] = []; current_url: Optional[str] = url_base; page_count = 0
    logger.info(f"Listando eventos para '{mailbox}' entre '{start_utc_str}' y '{end_utc_str}' (Display TZ: {timezone_display})")
    try:
        while current_url and len(all_events) < max_items_total:
            page_count += 1; params_for_call = query_params if current_url == url_base and page_count == 1 else None
            logger.debug(f" Obteniendo página {page_count} de eventos desde: {current_url}")
            response_data = hacer_llamada_api("GET", current_url, request_headers, params=params_for_call, timeout=GRAPH_API_DEFAULT_TIMEOUT)
            if response_data and isinstance(response_data, dict) and 'value' in response_data:
                items_in_page = response_data.get('value', []);
                if not isinstance(items_in_page, list): break
                for item in items_in_page:
                    if len(all_events) < max_items_total: all_events.append(item)
                    else: break
                current_url = response_data.get('@odata.nextLink')
                if not current_url or len(all_events) >= max_items_total: break
            else: break
        logger.info(f"Total eventos recuperados: {len(all_events)} ({page_count} pág).")
        return {"status": "success", "data": all_events, "total_retrieved": len(all_events), "pages_processed": page_count}
    except Exception as e:
        logger.error(f"Error listando eventos: {type(e).__name__} - {e}", exc_info=True); details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al listar eventos: {type(e).__name__}", "http_status": status_code, "details": details}

def crear_evento(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    mailbox: str = parametros.get('mailbox', 'me'); titulo: Optional[str] = parametros.get('titulo')
    inicio_str: Optional[str] = parametros.get('inicio'); fin_str: Optional[str] = parametros.get('fin')
    timezone_evento: str = "UTC" # Graph recomienda crear en UTC
    cuerpo_contenido: Optional[str] = parametros.get('cuerpo_contenido')
    cuerpo_tipo: str = parametros.get('cuerpo_tipo', 'HTML').upper()
    asistentes_in = parametros.get('asistentes'); ubicacion_display_name: Optional[str] = parametros.get('ubicacion')
    es_reunion_online: bool = str(parametros.get('es_reunion_online', "false")).lower() == "true"
    recordatorio_minutos: Optional[Any] = parametros.get('recordatorio_minutos')
    mostrar_como: str = parametros.get('mostrar_como', "busy")

    if not titulo or not inicio_str or not fin_str: return {"status": "error", "message": "Params 'titulo', 'inicio', 'fin' requeridos."}
    if cuerpo_tipo not in ["HTML", "TEXT"]: return {"status": "error", "message": "'cuerpo_tipo' debe ser HTML o Text."}
    try:
        start_utc_str = _parse_and_utc_datetime_str(inicio_str, "inicio")
        end_utc_str = _parse_and_utc_datetime_str(fin_str, "fin")
        if not start_utc_str or not end_utc_str : raise ValueError("Fechas inválidas.")
        if datetime.fromisoformat(end_utc_str.replace('Z', '+00:00')) <= datetime.fromisoformat(start_utc_str.replace('Z', '+00:00')):
            return {"status": "error", "message": "'fin' debe ser posterior a 'inicio'."}
    except ValueError as ve: return {"status": "error", "message": str(ve)}

    asistentes_list = _normalize_recipients(asistentes_in, "asistentes")
    event_payload: Dict[str, Any] = {"subject": titulo, "start": {"dateTime": start_utc_str, "timeZone": timezone_evento}, "end": {"dateTime": end_utc_str, "timeZone": timezone_evento}}
    if cuerpo_contenido: event_payload["body"] = {"contentType": cuerpo_tipo, "content": cuerpo_contenido}
    if asistentes_list: event_payload["attendees"] = asistentes_list
    if ubicacion_display_name: event_payload["location"] = {"displayName": ubicacion_display_name}
    if es_reunion_online: event_payload["isOnlineMeeting"] = True; event_payload["onlineMeetingProvider"] = "teamsForBusiness"
    event_payload["showAs"] = mostrar_como
    if recordatorio_minutos is not None:
        try: rem_val = int(recordatorio_minutos); event_payload["isReminderOn"] = True; event_payload["reminderMinutesBeforeStart"] = rem_val
        except ValueError: logger.warning(f"Valor inválido para 'recordatorio_minutos': {recordatorio_minutos}. Ignorando."); event_payload["isReminderOn"] = False
    else: event_payload["isReminderOn"] = False

    url = f"{BASE_URL}/users/{mailbox}/events"
    logger.info(f"Creando evento '{titulo}' para '{mailbox}'")
    try:
        created_event = hacer_llamada_api("POST", url, headers, json_data=event_payload, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": created_event, "message": "Evento creado."}
    except Exception as e:
        logger.error(f"Error creando evento: {type(e).__name__} - {e}", exc_info=True); details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al crear evento: {type(e).__name__}", "http_status": status_code, "details": details}

def obtener_evento(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Función auxiliar para obtener un evento por ID (útil después de PATCH 204)."""
    mailbox: str = parametros.get('mailbox', 'me')
    evento_id: Optional[str] = parametros.get('evento_id')
    select: Optional[str] = parametros.get('select')
    if not evento_id: return {"status": "error", "message": "Parámetro 'evento_id' requerido."}
    url = f"{BASE_URL}/users/{mailbox}/events/{evento_id}"; params_query = {'$select': select} if select else None
    logger.info(f"Obteniendo detalles del evento '{evento_id}' para '{mailbox}'")
    try:
        event_data = hacer_llamada_api("GET", url, headers, params=params_query, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        if event_data and isinstance(event_data, dict): return {"status": "success", "data": event_data}
        else: return {"status": "error", "message": f"No se pudo obtener el evento '{evento_id}'."}
    except Exception as e:
        logger.error(f"Error obteniendo evento '{evento_id}': {type(e).__name__} - {e}", exc_info=True); details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            if status_code == 404: return {"status": "error", "message": f"Evento '{evento_id}' no encontrado.", "details": details}
        return {"status": "error", "message": f"Error al obtener evento: {type(e).__name__}", "http_status": status_code, "details": details}


def actualizar_evento(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    mailbox: str = parametros.get('mailbox', 'me'); evento_id: Optional[str] = parametros.get('evento_id')
    nuevos_valores: Optional[Dict[str, Any]] = parametros.get('nuevos_valores'); etag: Optional[str] = parametros.get('etag')
    if not evento_id or not nuevos_valores or not isinstance(nuevos_valores, dict):
        return {"status": "error", "message": "Params 'evento_id' y 'nuevos_valores' (dict) requeridos."}

    payload_update = nuevos_valores.copy()
    try: # Normalizar fechas/horas en el payload a UTC string
        if 'start' in payload_update and isinstance(payload_update['start'], dict) and 'dateTime' in payload_update['start']:
            start_utc_str = _parse_and_utc_datetime_str(payload_update['start']['dateTime'], "nuevos_valores.start.dateTime")
            payload_update['start'] = {"dateTime": start_utc_str, "timeZone": "UTC"}
        if 'end' in payload_update and isinstance(payload_update['end'], dict) and 'dateTime' in payload_update['end']:
            end_utc_str = _parse_and_utc_datetime_str(payload_update['end']['dateTime'], "nuevos_valores.end.dateTime")
            payload_update['end'] = {"dateTime": end_utc_str, "timeZone": "UTC"}
    except ValueError as ve: return {"status": "error", "message": str(ve)}

    current_headers = headers.copy(); final_etag = etag or payload_update.pop('@odata.etag', None)
    if final_etag: current_headers['If-Match'] = final_etag; logger.debug(f"Usando ETag '{final_etag}'.")
    
    url = f"{BASE_URL}/users/{mailbox}/events/{evento_id}"
    logger.info(f"Actualizando evento '{evento_id}' para '{mailbox}'")
    try:
        updated_event_data = hacer_llamada_api("PATCH", url, current_headers, json_data=payload_update, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        if updated_event_data is None: # 204 No Content
            logger.info(f"Evento '{evento_id}' actualizado (204). Re-obteniendo datos...")
            return obtener_evento({"mailbox": mailbox, "evento_id": evento_id}, headers) # Re-obtener
        return {"status": "success", "data": updated_event_data, "message": "Evento actualizado."}
    except Exception as e:
        logger.error(f"Error actualizando evento '{evento_id}': {type(e).__name__} - {e}", exc_info=True); details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            if status_code in [404, 412]: msg = "no encontrado" if status_code==404 else "conflicto ETag"
            else: msg = f"Error al actualizar evento: {type(e).__name__}"
            return {"status": "error", "message": msg, "http_status": status_code, "details": details}
        return {"status": "error", "message": f"Error al actualizar evento: {type(e).__name__}", "details": details}

def eliminar_evento(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    mailbox: str = parametros.get('mailbox', 'me'); evento_id: Optional[str] = parametros.get('evento_id')
    etag: Optional[str] = parametros.get('etag')
    if not evento_id: return {"status": "error", "message": "Parámetro 'evento_id' requerido."}

    url = f"{BASE_URL}/users/{mailbox}/events/{evento_id}"
    current_headers = headers.copy()
    if etag: current_headers['If-Match'] = etag; logger.debug(f"Usando ETag '{etag}'.")
    
    logger.info(f"Eliminando evento '{evento_id}' para '{mailbox}'")
    try:
        hacer_llamada_api("DELETE", url, current_headers, timeout=GRAPH_API_DEFAULT_TIMEOUT, expect_json=False)
        return {"status": "success", "message": f"Evento '{evento_id}' eliminado."}
    except Exception as e:
        logger.error(f"Error eliminando evento '{evento_id}': {type(e).__name__} - {e}", exc_info=True); details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            if status_code in [404, 412]: msg = "no encontrado" if status_code==404 else "conflicto ETag"
            else: msg = f"Error al eliminar evento: {type(e).__name__}"
            return {"status": "error", "message": msg, "http_status": status_code, "details": details}
        return {"status": "error", "message": f"Error al eliminar evento: {type(e).__name__}", "details": details}


def crear_reunion_teams(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Wrapper para crear un evento que es una reunión de Teams."""
    logger.info("Wrapper: Llamando a 'crear_evento' para generar reunión Teams.")
    params_reunion = parametros.copy()
    params_reunion['es_reunion_online'] = True
    params_reunion['proveedor_reunion_online'] = "teamsForBusiness"
    return crear_evento(params_reunion, headers)

# --- FIN DEL MÓDULO actions/calendario_actions.py ---