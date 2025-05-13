import logging
import requests # Aún lo necesitamos para importar las excepciones específicas

# Importación relativa corregida para constants (sube 1 nivel a MyHttpTrigger, baja a shared)
from ..shared import constants
# Importamos nuestro cliente HTTP desde su nueva ubicación
from ..shared.helpers.http_client import AuthenticatedHttpClient

# Configuración del logger para este módulo
logger = logging.getLogger(__name__)

def calendar_list_events(client: AuthenticatedHttpClient, params: dict) -> dict:
    """
    Lista los eventos del calendario usando el cliente HTTP autenticado.

    Args:
        client (AuthenticatedHttpClient): Instancia del cliente HTTP autenticado.
        params (dict): Diccionario de parámetros. Puede incluir:
                       - 'top': (opcional) número de eventos a retornar.
                       - 'select': (opcional) campos específicos a seleccionar.
                       - 'filter': (opcional) para filtrar eventos (ej. por fecha).
                       - 'orderby': (opcional) para ordenar los resultados.

    Returns:
        dict: Respuesta JSON de la API de Graph o un diccionario de error.
    """
    try:
        list_events_url = f"{constants.GRAPH_API_BASE_URL}/me/events"
        
        # Construir parámetros de consulta de forma segura para Graph API ($)
        query_params = {}
        if params.get('top'):
            query_params['$top'] = params['top']
        if params.get('select'):
            query_params['$select'] = params['select']
        if params.get('filter'):
            query_params['$filter'] = params['filter']
        if params.get('orderby'):
            query_params['$orderby'] = params['orderby']

        logger.info(f"Solicitando eventos del calendario. URL: {list_events_url}, Params: {query_params}")
        
        # Usar el método get del cliente autenticado
        response = client.get(
            url=list_events_url,
            scope=constants.GRAPH_API_DEFAULT_SCOPE, # Especificar el scope necesario
            params=query_params
            # El timeout se maneja dentro del cliente si usamos su default
        )
        
        # raise_for_status() ya se llama dentro de client.get/request
        
        response_json = response.json()
        logger.info(f"Eventos del calendario obtenidos exitosamente. Count: {len(response_json.get('value', []))}")
        return response_json

    except requests.exceptions.HTTPError as http_err:
        # El error ya fue logueado por el http_client, pero podemos añadir contexto
        logger.error(f"Error HTTP al listar eventos del calendario (controlador): {http_err}")
        return {"error": "HTTPError", "status_code": http_err.response.status_code, "message": http_err.response.text}
    except requests.exceptions.RequestException as req_err:
        # El error ya fue logueado por el http_client
        logger.error(f"Error de conexión al listar eventos del calendario (controlador): {req_err}")
        return {"error": "RequestException", "message": str(req_err)}
    except ValueError as val_err: # Captura el error si el token no se pudo obtener
         logger.error(f"Error de valor (posiblemente token) al listar eventos (controlador): {val_err}")
         return {"error": "AuthenticationError", "message": str(val_err), "status_code": 500}
    except Exception as e:
        logger.exception(f"Error inesperado al listar eventos del calendario: {e}")
        return {"error": "UnexpectedError", "message": str(e), "status_code": 500}

def calendar_create_event(client: AuthenticatedHttpClient, params: dict) -> dict:
    """
    Crea un nuevo evento en el calendario usando el cliente HTTP autenticado.

    Args:
        client (AuthenticatedHttpClient): Instancia del cliente HTTP autenticado.
        params (dict): Diccionario con los detalles del evento a crear (cuerpo JSON).

    Returns:
        dict: Respuesta JSON de la API de Graph con el evento creado o un diccionario de error.
    """
    try:
        create_event_url = f"{constants.GRAPH_API_BASE_URL}/me/events"
        
        # Validar que los parámetros necesarios para crear el evento están presentes
        required_fields = ["subject", "start", "end"]
        if not all(field in params for field in required_fields):
            logger.error("Faltan campos requeridos para crear el evento (subject, start, end).")
            return {"error": "MissingParameters", "message": "Faltan campos requeridos: subject, start, end.", "status_code": 400}

        logger.info(f"Creando evento en el calendario. URL: {create_event_url}, Evento: {params.get('subject')}")
        
        # Usar el método post del cliente autenticado
        response = client.post(
            url=create_event_url,
            scope=constants.GRAPH_API_DEFAULT_SCOPE, # Especificar el scope necesario
            json=params # Pasar el cuerpo del evento como JSON
        )
        
        # raise_for_status() ya se llama dentro de client.post/request

        response_json = response.json()
        logger.info(f"Evento '{params.get('subject')}' creado exitosamente. ID: {response_json.get('id')}")
        return response_json

    except requests.exceptions.HTTPError as http_err:
        logger.error(f"Error HTTP al crear evento (controlador): {http_err}")
        return {"error": "HTTPError", "status_code": http_err.response.status_code, "message": http_err.response.text}
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Error de conexión al crear evento (controlador): {req_err}")
        return {"error": "RequestException", "message": str(req_err)}
    except ValueError as val_err: # Captura el error si el token no se pudo obtener
         logger.error(f"Error de valor (posiblemente token) al crear evento (controlador): {val_err}")
         return {"error": "AuthenticationError", "message": str(val_err), "status_code": 500}
    except Exception as e:
        logger.exception(f"Error inesperado al crear evento: {e}")
        return {"error": "UnexpectedError", "message": str(e), "status_code": 500}