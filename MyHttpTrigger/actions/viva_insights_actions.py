# MyHttpTrigger/actions/viva_insights_actions.py
import logging
import requests # Solo para tipos de excepción
import json
from typing import Dict, List, Optional, Any

# Importar helper y constantes
try:
    from ..shared.helpers.http_client import hacer_llamada_api
    from ..shared.constants import BASE_URL, GRAPH_API_DEFAULT_TIMEOUT, APP_NAME
    # Podríamos necesitar _parse_and_utc_datetime_str si manejamos fechas aquí
    from ..actions.calendario_actions import _parse_and_utc_datetime_str 
except ImportError as e:
    logging.critical(f"Error CRÍTICO importando dependencias compartidas en VivaInsights: {e}.", exc_info=True)
    BASE_URL = "https://graph.microsoft.com/v1.0"
    GRAPH_API_DEFAULT_TIMEOUT = 60
    APP_NAME = "EliteDynamicsPro" # Fallback
    # Crear un dummy de _parse_and_utc_datetime_str si la importación falla
    def _parse_and_utc_datetime_str(dt_str, name): raise ValueError("Helper de fecha no disponible")
    raise ImportError(f"No se pudo importar 'hacer_llamada_api', constantes o helpers de calendario: {e}") from e

logger = logging.getLogger(f"{APP_NAME}.actions.viva_insights")

# ---- FUNCIONES DE ACCIÓN PARA VIVA INSIGHTS (/me/analytics) ----
# Requieren permiso delegado Analytics.Read

def obtener_estadisticas_actividad(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Obtiene estadísticas de actividad agregadas para el usuario autenticado.
    Permite filtrar por tipo de actividad y/o rango de fechas.

    Args:
        parametros (Dict[str, Any]):
            'activity_type' (str, opcional): Filtrar por tipo de actividad. Valores comunes:
                'emailsSent', 'emailsReceived', 'meetingsAttended', 'meetingHours',
                'focusHours', 'collaborationHours', 'afterHoursWork', etc.
            'start_date' (str ISO, opcional): Fecha de inicio (YYYY-MM-DD).
            'end_date' (str ISO, opcional): Fecha de fin (YYYY-MM-DD).
            'top' (int, opcional): Máximo número de registros de estadísticas a devolver. Default 25.
            'select' (str, opcional): Campos específicos a seleccionar.
        headers (Dict[str, str]): Cabeceras con token OBO.

    Returns:
        Dict[str, Any]: {"status": "success", "data": [lista_estadisticas]} o error.
    """
    activity_type: Optional[str] = parametros.get('activity_type')
    start_date_str: Optional[str] = parametros.get('start_date')
    end_date_str: Optional[str] = parametros.get('end_date')
    top: int = min(int(parametros.get('top', 25)), 999)
    select: Optional[str] = parametros.get('select') # Ej: "activity,startDate,endDate,timeZoneUsed,duration"

    url = f"{BASE_URL}/me/analytics/activityStatistics"
    
    filters: List[str] = []
    if activity_type:
        filters.append(f"activity eq '{activity_type}'")
    try:
        # Validar y usar solo la parte de fecha (YYYY-MM-DD) para los filtros de fecha
        if start_date_str:
            parsed_start = _parse_and_utc_datetime_str(start_date_str, "start_date") # Parsea ISO datetime
            if parsed_start: filters.append(f"startDate eq {parsed_start[:10]}") # Usar solo YYYY-MM-DD
        if end_date_str:
            parsed_end = _parse_and_utc_datetime_str(end_date_str, "end_date")
            if parsed_end: filters.append(f"endDate eq {parsed_end[:10]}") # Usar solo YYYY-MM-DD
    except ValueError as ve:
         return {"status": "error", "message": f"Error en formato de fecha: {ve}"}

    query_params: Dict[str, Any] = {'$top': top}
    if filters:
        query_params['$filter'] = " and ".join(filters)
    if select:
        query_params['$select'] = select
        
    # Podría necesitarse $orderby si se esperan múltiples resultados por día/actividad
    # query_params['$orderby'] = "endDate desc" 

    log_filter_desc = f"(Filtro: {' y '.join(filters) if filters else 'ninguno'}, Top: {top})"
    logger.info(f"Obteniendo estadísticas de actividad Viva Insights para /me {log_filter_desc}")
    
    try:
        # La paginación podría aplicar aquí si se esperan muchos registros de actividad
        # Por ahora, solo obtenemos la primera página hasta 'top'
        response_data = hacer_llamada_api("GET", url, headers, params=query_params, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        # Devolver la lista de estadísticas encontradas
        return {"status": "success", "data": response_data.get("value", []) if isinstance(response_data, dict) else response_data}
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas Viva Insights: {type(e).__name__} - {e}", exc_info=True)
        details = str(e); status_code=500
        if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
            status_code = e.response.status_code; try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
            if status_code == 403: # Forbidden, usualmente por falta de licencia o permiso Analytics.Read
                 return {"status": "error", "message": f"Permiso denegado ({status_code}) para obtener estadísticas Viva. Verifica permisos y licencia.", "details": details}
        return {"status": "error", "message": f"Error al obtener estadísticas Viva Insights: {type(e).__name__}", "http_status": status_code, "details": details}

# --- Aquí se podrían añadir otras funciones si exploramos más la API de /me/analytics ---
# Ejemplos (requieren investigar más la API):
# def obtener_recomendaciones_bienestar(parametros, headers): ...
# def listar_patrones_trabajo(parametros, headers): ...

# --- FIN DEL MÓDULO actions/viva_insights_actions.py ---