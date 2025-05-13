# MyHttpTrigger/actions/vivainsights_actions.py
import logging
import requests # Para requests.exceptions.HTTPError
from typing import Dict, List, Optional, Any

# Importar el cliente autenticado y las constantes
from ..shared.helpers.http_client import AuthenticatedHttpClient
from ..shared import constants

logger = logging.getLogger(__name__)

# --- FUNCIONES DE ACCIÓN PARA VIVA INSIGHTS ---

def get_my_analytics(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Obtiene las estadísticas de actividad del usuario autenticado desde Viva Insights.
    Esto incluye tiempo dedicado a correos, reuniones, tiempo de concentración, etc.
    Corresponde al endpoint /me/analytics/activityStatistics.
    """
    # Parámetros de la API (ej. para filtrar por periodo, aunque activityStatistics no lo soporta directamente en /me)
    # El endpoint /me/analytics/activityStatistics devuelve un conjunto de estadísticas predefinidas.
    # Para filtrar por fechas, se necesitaría un endpoint más granular o procesar los datos después.
    # select_fields: Optional[str] = params.get("select") # No aplica directamente a este endpoint de la misma manera
    
    # activityStatistics es un recurso singular, no una colección paginada por defecto.
    # Sin embargo, devuelve una colección de activityStatistics.
    # https://learn.microsoft.com/en-us/graph/api/useranalytics-list-activitystatistics?view=graph-rest-1.0&tabs=http
    # El endpoint /me/analytics/activityStatistics devuelve TODAS las estadísticas de actividad para el usuario.
    
    url = f"{constants.GRAPH_API_BASE_URL}/me/analytics/activityStatistics"
    
    # Construir parámetros de query si son necesarios y soportados por el endpoint
    api_query_params: Dict[str, Any] = {}
    # Ejemplo: Si la API soportara $filter por activity o startDate (revisar documentación de Graph)
    # if params.get('filter_activity'):
    #     api_query_params['$filter'] = f"activity eq '{params['filter_activity']}'"

    logger.info(f"Obteniendo estadísticas de actividad de Viva Insights para el usuario actual (/me/analytics/activityStatistics)")
    try:
        response = client.get(url, scope=constants.GRAPH_SCOPE, params=api_query_params if api_query_params else None)
        analytics_data = response.json()
        # La respuesta es una colección de objetos activityStatistic
        return {"status": "success", "data": analytics_data.get("value", [])}
    except requests.exceptions.HTTPError as http_err:
        error_details = http_err.response.text if http_err.response else "No response body"
        status_code_resp = http_err.response.status_code if http_err.response else 500
        logger.error(f"Error HTTP obteniendo analíticas de Viva Insights: {status_code_resp} - {error_details[:300]}", exc_info=False)
        if status_code_resp == 403: # Forbidden, puede que Viva Insights no esté habilitado o licenciado
             return {"status": "error", "message": "Acceso prohibido a Viva Insights. Verifique la licencia y configuración.", "http_status": 403, "details": error_details}
        return {"status": "error", "message": f"Error HTTP: {status_code_resp}", "details": error_details, "http_status": status_code_resp}
    except Exception as e:
        logger.error(f"Error obteniendo analíticas de Viva Insights: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al obtener analíticas de Viva Insights: {type(e).__name__}", "details": str(e)}

def get_focus_plan(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Obtiene información relacionada con el tiempo de concentración (focus time) del usuario.
    Actualmente, esto devuelve las estadísticas de actividad que incluyen 'focusHours'.
    La configuración detallada del plan de concentración (cómo se agenda, etc.)
    generalmente se maneja dentro de la aplicación Viva Insights o Outlook, y no tiene
    un endpoint de API Graph simple para "obtener el plan configurado".

    Alternativamente, para ver el tiempo de concentración agendado, se podrían buscar
    eventos de calendario con la categoría "Tiempo de concentración".
    """
    logger.info("Intentando obtener información del plan de concentración (estadísticas de actividad de focus).")

    # Se reutiliza la lógica de get_my_analytics ya que 'focus' es una de las actividades allí.
    # O se podría llamar a un endpoint más específico si existiera y fuera necesario.
    # Por ahora, filtramos el resultado de activityStatistics.
    
    analytics_result = get_my_analytics(client, params) # Reutiliza la función anterior

    if analytics_result.get("status") == "success":
        all_activities_stats = analytics_result.get("data", [])
        focus_stats: List[Dict[str, Any]] = []
        
        if isinstance(all_activities_stats, list):
            for stat_entry in all_activities_stats:
                if isinstance(stat_entry, dict) and stat_entry.get("activity") == "focus":
                    focus_stats.append(stat_entry)
        
        if focus_stats:
            logger.info(f"Estadísticas de tiempo de concentración encontradas: {focus_stats}")
            return {
                "status": "success", 
                "data": focus_stats, 
                "message": "Estadísticas de tiempo de concentración obtenidas. Para ver eventos de calendario de focus, use calendar_list_events con el filtro apropiado."
            }
        else:
            logger.info("No se encontraron estadísticas específicas para la actividad 'focus' en los datos de analíticas.")
            return {
                "status": "success", # La llamada a analytics fue exitosa, pero no hay datos de focus.
                "data": [],
                "message": "No se encontraron estadísticas específicas para la actividad 'focus'. El plan podría no estar activo o no haber datos recientes."
            }
    else:
        # Propagar el error de get_my_analytics
        logger.error(f"No se pudo obtener la información del plan de concentración porque falló la obtención de analíticas: {analytics_result.get('message')}")
        return analytics_result


# --- FIN DEL MÓDULO actions/vivainsights_actions.py ---