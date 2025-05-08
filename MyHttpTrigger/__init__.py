# MyHttpTrigger/__init__.py (VERSIÓN CORRECTA Y FINAL)
import logging
import azure.functions as func
import os
import json

# --- Importaciones MSAL Corregidas y Completas ---
from msal import ConfidentialClientApplication
# Importar TODAS las excepciones MSAL específicas desde msal.exceptions
from msal.exceptions import MsalUiRequiredException, MsalServiceError
# --- Fin Importaciones MSAL Corregidas ---

# Importar constantes y el alias del ejecutor
try:
    # Asume que estos módulos existen en las rutas correctas ahora
    from .shared.constants import GRAPH_API_DEFAULT_SCOPE, AZURE_OPENAI_DEFAULT_SCOPE, APP_NAME
    from .mapping_actions import available_actions
    from .ejecutor import execute_action as execute_action_func

    # Definir logger_init aquí si las importaciones básicas funcionan
    logger_name_init = f"{APP_NAME}.HttpTrigger"
    logger_init = logging.getLogger(logger_name_init)

except ImportError as e:
    # Si las importaciones iniciales fallan, usa un logger de fallback
    # Esto es crucial si, por ejemplo, constants.py tiene un error.
    logger_init = logging.getLogger("EliteDynamicsPro.StartupErrorLogger")
    logger_init.critical(f"FALLO CRÍTICO AL IMPORTAR MODULOS BASE (__init__.py): {type(e).__name__}: {e}. "
                     "La función no operará correctamente.", exc_info=True)
    available_actions = {} # Define como vacío para evitar NameError
    # Define una función dummy para que la llamada a execute_action_func no falle por NameError
    def dummy_execute_action_on_base_import_error(action_name, parametros, headers, actions_map):
        logging.error("EJECUTOR DUMMY (desde __init__): Llamado debido a fallo crítico en importación de módulos base (mapping/ejecutor).")
        return {"status": "error", "message": "Error crítico de configuración interna del servidor (fallo de importación de módulos base)."}
    execute_action_func = dummy_execute_action_on_base_import_error
except Exception as e:
    # Captura cualquier otra excepción inesperada durante la carga inicial
    logger_init = logging.getLogger("EliteDynamicsPro.StartupCriticalExceptionLogger")
    logger_init.critical(f"EXCEPCIÓN INESPERADA CRÍTICA durante importaciones en MyHttpTrigger/__init__.py: {e}", exc_info=True)
    available_actions = {}
    def dummy_execute_action_on_startup_exception(action_name, parametros, headers, actions_map):
        logging.error("EJECUTOR DUMMY (desde __init__): Llamado debido a excepción crítica en carga de módulos.")
        return {"status": "error", "message": "Error crítico de configuración interna del servidor (excepción en carga de módulos)."}
    execute_action_func = dummy_execute_action_on_startup_exception

def main(req: func.HttpRequest) -> func.HttpResponse:
    # Asegurar que el logger esté disponible, incluso si falló la importación de APP_NAME
    global logger_init
    if not logger_init or logger_init.name.startswith("EliteDynamicsPro.Startup"): # Si usamos el logger de error o no se inicializó
        try: current_app_name = APP_NAME
        except NameError: current_app_name = "EliteDynamicsPro"
        logger_init = logging.getLogger(f"{current_app_name}.HttpTrigger.main") # Obtener el logger correcto

    request_id = req.headers.get("X-Request-ID", os.urandom(8).hex())
    logger_init.info(f"Python HTTP trigger procesando petición. RequestId: {request_id}, URL: {req.url}, Method: {req.method}")

    # 1. Validar carga de componentes críticos
    if not available_actions or not callable(execute_action_func) or execute_action_func.__name__.startswith("dummy_execute"):
        logger_init.critical(f"RequestId: {request_id} - Error Crítico: Módulos/Ejecutor no disponibles o dummies. Revisar logs de inicio.")
        return func.HttpResponse(json.dumps({"error": "Error interno servidor", "message": "Componentes críticos no cargados."}), status_code=500, mimetype="application/json")
    logger_init.info(f"RequestId: {request_id} - Módulos cargados. Acciones: {list(available_actions.keys())}")

    # 2. Obtener token de usuario
    auth_header = req.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        logger_init.warning(f"RequestId: {request_id} - Falta token Bearer.")
        return func.HttpResponse(json.dumps({"error": "Unauthorized", "message": "Token Bearer requerido."}), status_code=401, mimetype="application/json")
    user_assertion_token = auth_header.split(' ')[1]

    # 3. Procesar cuerpo JSON
    try:
        req_body = req.get_json(); action_name = req_body.get('action'); action_params = req_body.get('params', {})
        target_service_for_obo = req_body.get('target_service', 'graph').lower()
        if not action_name: return func.HttpResponse(json.dumps({"error": "Solicitud inválida", "message": "'action' requerido."}), status_code=400, mimetype="application/json")
        if not isinstance(action_params, dict): return func.HttpResponse(json.dumps({"error": "Solicitud inválida", "message": "'params' debe ser un objeto."}), status_code=400, mimetype="application/json")
    except ValueError as e:
        logger_init.warning(f"RequestId: {request_id} - Error parseando JSON: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Solicitud inválida", "message": f"Cuerpo JSON malformado: {e}"}), status_code=400, mimetype="application/json")

    # 4. Lógica OBO
    final_auth_token_for_action = None
    try:
        client_id = os.environ["CLIENT_ID"]; client_secret = os.environ["CLIENT_SECRET"]; tenant_id = os.environ["TENANT_ID"]
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        if target_service_for_obo == 'openai': current_obo_scope = AZURE_OPENAI_DEFAULT_SCOPE
        elif target_service_for_obo == 'graph': current_obo_scope = GRAPH_API_DEFAULT_SCOPE
        else: current_obo_scope = GRAPH_API_DEFAULT_SCOPE; logger_init.warning(f"Target service '{target_service_for_obo}' no reconocido, usando scope Graph.")
        
        logger_init.info(f"RequestId: {request_id} - Intentando OBO para target '{target_service_for_obo}' scope: {current_obo_scope}")
        cca = ConfidentialClientApplication(client_id, authority=authority, client_credential=client_secret)
        result = cca.acquire_token_on_behalf_of(user_assertion=user_assertion_token, scopes=current_obo_scope)

        if "access_token" in result: final_auth_token_for_action = result['access_token']; logger_init.info(f"RequestId: {request_id} - Token OBO adquirido.")
        elif "error" in result:
            err_code=result.get('error'); err_desc=result.get('error_description','N/A'); sub_err=result.get('suberror')
            logger_init.error(f"RequestId: {request_id} - Error MSAL OBO: Code='{err_code}', SubErr='{sub_err}', Desc='{err_desc}'")
            http_status=403; msg=f"Fallo OBO ({err_code})."
            if "AADSTS50027" in err_desc or "invalid_grant" in err_code: http_status=401; msg="Token usuario inválido/expirado."
            elif "AADSTS65001" in err_desc: msg="Consentimiento requerido."
            return func.HttpResponse(json.dumps({"error": "Fallo OBO", "message": msg, "details": err_desc}), status_code=http_status, mimetype="application/json")
        else:
            logger_init.error(f"RequestId: {request_id} - Respuesta MSAL OBO inesperada: {result}")
            return func.HttpResponse(json.dumps({"error": "Fallo OBO", "message": "Respuesta auth inesperada."}), status_code=500, mimetype="application/json")

    except MsalUiRequiredException as e: # Captura específica
        logger_init.error(f"RequestId: {request_id} - Error MSAL OBO (Consentimiento/Interacción): {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Consentimiento Requerido", "message": "Permisos o interacción requerida.", "details": str(e)}), status_code=403, mimetype="application/json")
    except MsalServiceError as e: # Captura otros errores MSAL
        logger_init.error(f"RequestId: {request_id} - Error MSAL OBO (Servicio): {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Error Servicio Auth", "message": "Error en servicio de autenticación.", "details": str(e)}), status_code=500, mimetype="application/json")
    except KeyError as e: # Falta variable de entorno
        logger_init.critical(f"RequestId: {request_id} - Falta variable de entorno para OBO: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Error Configuración Servidor", "message": f"Variable '{e}' no configurada."}), status_code=500, mimetype="application/json")
    except Exception as e: # Captura genérica final
        logger_init.critical(f"RequestId: {request_id} - Excepción general OBO: {type(e).__name__} - {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Error Interno Auth", "message": "Excepción durante OBO."}), status_code=500, mimetype="application/json")

    if not final_auth_token_for_action:
        logger_init.critical(f"RequestId: {request_id} - Token OBO final es None.")
        return func.HttpResponse(json.dumps({"error": "Error Interno Crítico", "message": "Falló obtención token."}), status_code=500, mimetype="application/json")

    # 5. Preparar cabeceras y ejecutar acción
    action_headers = {'Authorization': f'Bearer {final_auth_token_for_action}', 'Content-Type': 'application/json'}
    logger_init.info(f"RequestId: {request_id} - Llamando ejecutor para acción: '{action_name}'")
    action_result = execute_action_func(action_name, action_params, action_headers, available_actions)

    # 6. Devolver resultado
    response_status_code = 500 # Default error
    if isinstance(action_result, dict):
        action_status = action_result.get("status", "undefined")
        if "success" in action_status: response_status_code = 200
        elif action_status == "error" and "Acción no encontrada" in action_result.get("message", ""): response_status_code = 404
    logger_init.info(f"RequestId: {request_id} - Acción '{action_name}' completada. Devolviendo HTTP {response_status_code}.")
    return func.HttpResponse(json.dumps(action_result), status_code=response_status_code, mimetype="application/json")