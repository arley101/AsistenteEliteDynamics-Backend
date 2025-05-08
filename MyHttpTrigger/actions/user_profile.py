# MyHttpTrigger/actions/user_profile.py
import logging
import requests # Asegúrate que esté importado

logging.warning("--- DEBUG: Ejecutando user_profile.py ---")
# ... (tus otras importaciones si las hay) ...

# La función ahora recibe action_context
def get_my_profile(action_context: dict):
    logging.info("Ejecutando acción: get_my_profile")
    # Extraer el cliente y el endpoint del contexto
    graph_client = action_context["graph_client"]
    graph_api_endpoint = action_context["graph_api_endpoint"]

    try:
        # Construir URL completa y llamar a /me
        me_url = f"{graph_api_endpoint}/me?$select=displayName,mail,userPrincipalName"
        logging.info(f"Llamando a Graph API: GET {me_url}")
        user_data_response = graph_client.get(me_url)
        user_data_response.raise_for_status() # Lanza excepción si hubo error HTTP (4xx, 5xx)

        profile = user_data_response.json()
        logging.info(f"Perfil obtenido para: {profile.get('userPrincipalName')}")
        return {"status": "success", "data": profile}
    # Capturar errores de Request (red, HTTP > 400)
    except requests.exceptions.RequestException as e:
        logging.error(f"Error al llamar a Graph API ({me_url}): {e}")
        error_details = "No details"
        status_code = 500 # Default a error interno
        if e.response is not None:
            status_code = e.response.status_code # Usar status code real si está disponible
            try:
                error_details = e.response.json() # Intentar obtener cuerpo del error JSON
            except ValueError: # Si la respuesta no es JSON
                error_details = e.response.text
            logging.error(f"Respuesta de error de Graph ({status_code}): {error_details}")
        return {"status": "error", "message": f"Error al contactar Microsoft Graph ({status_code})", "details": error_details}
    # Capturar cualquier otro error inesperado
    except Exception as e:
        logging.error(f"Error inesperado en get_my_profile: {e}", exc_info=True)
        return {"status": "error", "message": f"Error inesperado en la acción: {type(e).__name__}"}

logging.warning("--- DEBUG: Fin de la definición de user_profile.py ---")