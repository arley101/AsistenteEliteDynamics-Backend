# MyHttpTrigger/actions/graph_test_actions.py
import logging
import requests 

logger = logging.getLogger("EliteDynamicsPro.GraphTestActions")

def obtener_perfil_identidad_administrada(params, headers):
    graph_url = "https://graph.microsoft.com/v1.0/me"
    try:
        logger.info(f"Acción 'obtener_perfil_identidad_administrada': Llamando a Graph API: {graph_url}")
        response = requests.get(graph_url, headers=headers)
        response.raise_for_status() 
        profile_data = response.json()
        logger.info("Acción 'obtener_perfil_identidad_administrada': Perfil obtenido exitosamente desde Graph.")
        return {"status": "success_managed_identity_profile_fetched", "data": profile_data}
    except requests.exceptions.HTTPError as http_err:
        error_details = "Sin detalles del cuerpo de la respuesta."
        try:
            error_details = http_err.response.json() 
        except ValueError: 
            error_details = http_err.response.text
        logger.error(f"Acción 'obtener_perfil_identidad_administrada': Error HTTP al llamar a /me: {http_err.response.status_code} - {error_details}", exc_info=True)
        return {"status": "error_graph_http_managed_identity_profile", "message": f"Error HTTP {http_err.response.status_code} al obtener perfil.", "details": error_details}
    except Exception as e:
        logger.error(f"Acción 'obtener_perfil_identidad_administrada': Error inesperado al llamar a /me: {e}", exc_info=True)
        return {"status": "error_graph_unexpected_managed_identity_profile", "message": f"Error inesperado al obtener perfil: {str(e)}"}