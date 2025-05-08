# MyHttpTrigger/actions/bookings_actions.py
import logging
import requests # Solo para tipos de excepción
import json
from typing import Dict, List, Optional, Any

# Importar helper y constantes
try:
    from ..shared.helpers.http_client import hacer_llamada_api
    from ..shared.constants import BASE_URL, GRAPH_API_DEFAULT_TIMEOUT, APP_NAME
except ImportError as e:
    logging.critical(f"Error CRÍTICO importando dependencias compartidas en Bookings: {e}.", exc_info=True)
    BASE_URL = "https://graph.microsoft.com/v1.0"
    GRAPH_API_DEFAULT_TIMEOUT = 60 # Timeout un poco más largo para Bookings
    APP_NAME = "EliteDynamicsPro" # Fallback
    raise ImportError(f"No se pudo importar 'hacer_llamada_api' o constantes: {e}") from e

logger = logging.getLogger(f"{APP_NAME}.actions.bookings")

# --- FUNCIONES DE ACCIÓN PARA MICROSOFT BOOKINGS ---
# Requieren permisos delegados como Bookings.Read.All, BookingsAppointment.ReadWrite.All, etc.

def listar_negocios_bookings(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Lista los negocios de Microsoft Bookings a los que el usuario tiene acceso.

    Args:
        parametros (Dict[str, Any]):
            'query' (str, opcional): Query OData para filtrar/buscar negocios (ej. "startsWith(displayName,'Contoso')").
            'select' (str, opcional): Campos a seleccionar.
            'top' (int, opcional): Número máximo de resultados.
        headers (Dict[str, str]): Cabeceras con token OBO.

    Returns:
        Dict[str, Any]: {"status": "success", "data": [lista_negocios]} o error.
    """
    query: Optional[str] = parametros.get("query")
    select: Optional[str] = parametros.get("select", "id,displayName,businessType,isPublished")
    top: int = min(int(parametros.get("top", 100)), 999)

    url = f"{BASE_URL}/solutions/bookingBusinesses"
    params_query: Dict[str, Any] = {'$top': top}
    if query: params_query['$filter'] = query # Usar $filter para buscar por nombre
    if select: params_query['$select'] = select

    logger.info(f"Listando negocios de Bookings (Query: '{query or 'N/A'}', Top: {top})")
    try:
        # La paginación completa podría requerir @odata.nextLink
        response_data = hacer_llamada_api("GET", url, headers, params=params_query, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": response_data.get("value", []) if isinstance(response_data, dict) else response_data}
    except Exception as e:
        logger.error(f"Error listando negocios de Bookings: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al listar negocios de Bookings: {type(e).__name__}", "http_status": status_code, "details": details}

def obtener_negocio_bookings(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Obtiene detalles de un negocio de Bookings específico por ID."""
    business_id: Optional[str] = parametros.get("business_id")
    if not business_id: return {"status": "error", "message": "Parámetro 'business_id' es requerido."}
    
    url = f"{BASE_URL}/solutions/bookingBusinesses/{business_id}"
    logger.info(f"Obteniendo detalles del negocio de Bookings '{business_id}'")
    try:
        business_data = hacer_llamada_api("GET", url, headers, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": business_data}
    except Exception as e:
        logger.error(f"Error obteniendo negocio de Bookings '{business_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            if status_code == 404: return {"status": "error", "message": f"Negocio de Bookings '{business_id}' no encontrado.", "details": details}
        return {"status": "error", "message": f"Error al obtener negocio de Bookings: {type(e).__name__}", "http_status": status_code, "details": details}

def listar_servicios_bookings(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Lista los servicios ofrecidos por un negocio de Bookings."""
    business_id: Optional[str] = parametros.get("business_id")
    if not business_id: return {"status": "error", "message": "Parámetro 'business_id' es requerido."}

    url = f"{BASE_URL}/solutions/bookingBusinesses/{business_id}/services"
    logger.info(f"Listando servicios del negocio de Bookings '{business_id}'")
    try:
        # Podría necesitar paginación si hay muchos servicios
        services_data = hacer_llamada_api("GET", url, headers, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": services_data.get("value", []) if isinstance(services_data, dict) else services_data}
    except Exception as e:
        logger.error(f"Error listando servicios Bookings '{business_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            if status_code == 404: return {"status": "error", "message": f"Negocio de Bookings '{business_id}' no encontrado.", "details": details}
        return {"status": "error", "message": f"Error al listar servicios Bookings: {type(e).__name__}", "http_status": status_code, "details": details}

def listar_citas_bookings(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Lista las citas para un negocio de Bookings en un rango de fechas (usando calendarView).

    Args:
        parametros (Dict[str, Any]):
            'business_id' (str): ID del negocio de Bookings. Requerido.
            'start_datetime' (str ISO): Fecha/hora de inicio del rango. Requerido.
            'end_datetime' (str ISO): Fecha/hora de fin del rango. Requerido.
            'timezone_display' (str, opcional): Timezone para la cabecera Prefer. Default "UTC".
            'top_per_page' (int, opcional): Citas por página. Default 25.
            'max_items_total' (int, opcional): Máximo total de citas a devolver. Default 100.
            'select' (str, opcional): Campos a seleccionar.
            'filter_query' (str, opcional): Filtro OData adicional.
            'order_by' (str, opcional): Campo para ordenar. Default 'start/dateTime asc'.
        headers (Dict[str, str]): Cabeceras con token OBO.
    """
    business_id: Optional[str] = parametros.get("business_id")
    start_datetime_str: Optional[str] = parametros.get('start_datetime')
    end_datetime_str: Optional[str] = parametros.get('end_datetime')
    timezone_display: str = parametros.get('timezone_display', 'UTC')
    top_per_page: int = min(int(parametros.get('top_per_page', 25)), 50)
    max_items_total: int = int(parametros.get('max_items_total', 100))
    select: Optional[str] = parametros.get('select')
    filter_query: Optional[str] = parametros.get('filter_query')
    order_by: Optional[str] = parametros.get('order_by', 'start/dateTime asc')

    if not business_id or not start_datetime_str or not end_datetime_str:
        return {"status": "error", "message": "Parámetros 'business_id', 'start_datetime' y 'end_datetime' son requeridos."}

    try:
        start_utc_str = _parse_and_utc_datetime_str(start_datetime_str, "start_datetime")
        end_utc_str = _parse_and_utc_datetime_str(end_datetime_str, "end_datetime")
        if not start_utc_str or not end_utc_str : raise ValueError("Fechas inválidas.")
    except ValueError as ve:
        return {"status": "error", "message": str(ve)}

    # Usar calendarView para obtener citas en un rango de tiempo
    url_base = f"{BASE_URL}/solutions/bookingBusinesses/{business_id}/calendarView"
    
    query_params: Dict[str, Any] = {
        'start': start_utc_str, # calendarView usa 'start' y 'end'
        'end': end_utc_str,
        '$top': top_per_page
    }
    if select: query_params['$select'] = select
    if filter_query: query_params['$filter'] = filter_query
    if order_by: query_params['$orderby'] = order_by
    
    request_headers = headers.copy()
    request_headers['Prefer'] = f'outlook.timezone="{timezone_display}"'

    all_appointments: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0
    
    logger.info(f"Listando citas Bookings para '{business_id}' entre '{start_utc_str}' y '{end_utc_str}'")
    try:
        while current_url and len(all_appointments) < max_items_total:
            page_count += 1
            params_for_call = query_params if current_url == url_base and page_count == 1 else None
            logger.debug(f" Obteniendo página {page_count} de citas Bookings desde: {current_url}")
            response_data = hacer_llamada_api("GET", current_url, request_headers, params=params_for_call, timeout=GRAPH_API_DEFAULT_TIMEOUT)

            if response_data and isinstance(response_data, dict) and 'value' in response_data:
                items_in_page = response_data.get('value', [])
                if not isinstance(items_in_page, list): break
                for item in items_in_page:
                    if len(all_appointments) < max_items_total: all_appointments.append(item)
                    else: break
                current_url = response_data.get('@odata.nextLink')
                if not current_url or len(all_appointments) >= max_items_total: break
            else: break
        
        logger.info(f"Total citas Bookings recuperadas: {len(all_appointments)} ({page_count} pág).")
        return {"status": "success", "data": all_appointments, "total_retrieved": len(all_appointments), "pages_processed": page_count}
    except Exception as e:
        logger.error(f"Error listando citas Bookings: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return {"status": "error", "message": f"Error al listar citas Bookings: {type(e).__name__}", "http_status": status_code, "details": details}

def crear_cita_bookings(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Crea una nueva cita en el calendario de un negocio de Bookings."""
    business_id: Optional[str] = parametros.get("business_id")
    # Información del cliente
    customer_email: Optional[str] = parametros.get("customer_email")
    customer_name: Optional[str] = parametros.get("customer_name")
    customer_phone: Optional[str] = parametros.get("customer_phone")
    customer_notes: Optional[str] = parametros.get("customer_notes")
    customer_timezone: str = parametros.get("customer_timezone", "UTC") # Timezone del cliente
    # Información de la cita
    service_id: Optional[str] = parametros.get("service_id") # ID del servicio de Bookings
    start_datetime_str: Optional[str] = parametros.get("start_datetime") # Hora de inicio en ISO 8601
    end_datetime_str: Optional[str] = parametros.get("end_datetime") # Hora de fin en ISO 8601
    staff_member_ids: Optional[List[str]] = parametros.get("staff_member_ids") # Lista de IDs de staff
    
    if not business_id or not customer_email or not customer_name or not service_id or not start_datetime_str or not end_datetime_str:
        return {"status": "error", "message": "Params 'business_id', 'customer_email', 'customer_name', 'service_id', 'start_datetime', 'end_datetime' requeridos."}

    try:
        start_utc_str = _parse_and_utc_datetime_str(start_datetime_str, "start_datetime")
        end_utc_str = _parse_and_utc_datetime_str(end_datetime_str, "end_datetime")
        if not start_utc_str or not end_utc_str : raise ValueError("Fechas inválidas.")
        if datetime.fromisoformat(end_utc_str.replace('Z', '+00:00')) <= datetime.fromisoformat(start_utc_str.replace('Z', '+00:00')):
             return {"status": "error", "message": "La fecha/hora 'end_datetime' debe ser posterior a 'start_datetime'."}
    except ValueError as ve:
        return {"status": "error", "message": str(ve)}

    url = f"{BASE_URL}/solutions/bookingBusinesses/{business_id}/appointments"
    
    appointment_payload = {
        "@odata.type": "#microsoft.graph.bookingAppointment", # Importante especificar tipo
        "customerId": None, # Si el cliente ya existe, se puede poner ID, si no, se crea uno implícitamente
        "customerEmailAddress": customer_email,
        "customerName": customer_name,
        "customerNotes": customer_notes,
        "customerPhone": customer_phone,
        "customerTimeZone": customer_timezone, # Timezone del cliente
        "serviceId": service_id,
        "startDateTime": {"dateTime": start_utc_str, "timeZone": "UTC"}, # Enviar a Graph en UTC
        "endDateTime": {"dateTime": end_utc_str, "timeZone": "UTC"},
        "staffMemberIds": staff_member_ids or [] # IDs del staff asignado
        # Otros campos opcionales: price, reminders, etc.
    }

    logger.info(f"Creando cita Booking para '{customer_name}' en negocio '{business_id}'")
    try:
        created_appointment = hacer_llamada_api("POST", url, headers, json_data=appointment_payload, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        return {"status": "success", "data": created_appointment, "message": "Cita de Bookings creada exitosamente."}
    except Exception as e:
        logger.error(f"Error creando cita Bookings: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            # Podrían haber errores específicos de Bookings (ej. conflicto horario, servicio inválido)
            if status_code == 400: return {"status": "error", "message": "Error en los datos de la cita (400).", "details": details}
            if status_code == 404: return {"status": "error", "message": f"Negocio o servicio Bookings no encontrado ({status_code}).", "details": details}
        return {"status": "error", "message": f"Error al crear cita Bookings: {type(e).__name__}", "http_status": status_code, "details": details}

def cancelar_cita_bookings(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Cancela una cita de Bookings existente."""
    business_id: Optional[str] = parametros.get("business_id")
    appointment_id: Optional[str] = parametros.get("appointment_id")
    cancellation_message: str = parametros.get("cancellation_message", "Cita cancelada por el asistente.") # Mensaje opcional

    if not business_id or not appointment_id:
        return {"status": "error", "message": "Parámetros 'business_id' y 'appointment_id' son requeridos."}
        
    url = f"{BASE_URL}/solutions/bookingBusinesses/{business_id}/appointments/{appointment_id}/cancel"
    body = {"cancellationMessage": cancellation_message}
    
    logger.info(f"Cancelando cita Bookings '{appointment_id}' en negocio '{business_id}'")
    try:
        # POST a /cancel devuelve 204 No Content
        hacer_llamada_api("POST", url, headers, json_data=body, timeout=GRAPH_API_DEFAULT_TIMEOUT, expect_json=False)
        return {"status": "success", "message": f"Cita '{appointment_id}' cancelada exitosamente."}
    except Exception as e:
        logger.error(f"Error cancelando cita Bookings '{appointment_id}': {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            if status_code == 404: return {"status": "error", "message": f"Cita '{appointment_id}' o negocio '{business_id}' no encontrado.", "details": details}
        return {"status": "error", "message": f"Error al cancelar cita Bookings: {type(e).__name__}", "http_status": status_code, "details": details}

# --- FIN DEL MÓDULO actions/bookings_actions.py ---