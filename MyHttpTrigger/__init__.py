# MyHttpTrigger/__init__.py (CON DIAGNÓSTICO INTEGRADO)
import logging
import azure.functions as func
import os
import json
import sys # Asegurarse de que sys está importado para el diagnóstico

# --- Inicio de código de depuración ---
def log_environment_details():
    logging.info("--- Environment Diagnostic Start ---")
    logging.info(f"Python version: {sys.version}")
    logging.info(f"sys.path: {sys.path}")
    
    pythonpath_env = os.environ.get('PYTHONPATH')
    logging.info(f"PYTHONPATH environment variable: {pythonpath_env if pythonpath_env else 'Not set'}")
    
    current_working_dir = os.getcwd()
    logging.info(f"Current working directory: {current_working_dir}")
    
    wwwroot_path = '/home/site/wwwroot' # Ruta estándar en App Service Linux
    if os.path.exists(wwwroot_path):
        logging.info(f"Contents of {wwwroot_path} (first 20 items): {os.listdir(wwwroot_path)[:20]}")
    else:
        logging.info(f"{wwwroot_path} not found.")
        
    # Ajusta la versión de Python aquí si es diferente a 3.11.
    # Tus logs de build de GitHub Actions indican python3.11.
    expected_packages_path_python_version = "python3.11" 
    
    possible_package_paths = [
        os.path.join(wwwroot_path, '.python_packages/lib', expected_packages_path_python_version, 'site-packages'),
        os.path.join(current_working_dir, '.python_packages/lib', expected_packages_path_python_version, 'site-packages')
    ]
    
    msal_found_in_any_path = False
    for path_to_check in possible_package_paths:
        if os.path.exists(path_to_check):
            logging.info(f"Found potential site-packages: {path_to_check}")
            logging.info(f"Contents of {path_to_check} (first 20 items): {os.listdir(path_to_check)[:20]}")
            msal_package_path = os.path.join(path_to_check, 'msal')
            if os.path.exists(msal_package_path):
                logging.info(f"MSAL directory FOUND at: {msal_package_path}")
                logging.info(f"Contents of msal directory (first 10 items): {os.listdir(msal_package_path)[:10]}")
                msal_found_in_any_path = True
            else:
                logging.warning(f"MSAL directory NOT FOUND at: {msal_package_path}")
        else:
            logging.info(f"Potential site-packages path does not exist: {path_to_check}")
    
    if not msal_found_in_any_path:
        logging.error("MSAL package directory was NOT FOUND in any of the checked standard paths.")
        
    logging.info("--- Environment Diagnostic End ---")

# Llamar a la función de diagnóstico al inicio del script del worker de Python
# Esto se ejecutará cuando el worker de Python cargue tu función por primera vez.
log_environment_details()
# --- Fin de código de depuración ---

# --- Importaciones MSAL Corregidas y Completas ---
# Intentaremos importar MSAL DESPUÉS del diagnóstico.
# Si esto falla, los logs de diagnóstico anteriores deberían darnos pistas.
try:
    from msal import ConfidentialClientApplication
    from msal.exceptions import MsalUiRequiredException, MsalServiceError
    logging.info("MSAL y excepciones MSAL importadas correctamente después del diagnóstico.")
except ModuleNotFoundError as e_msal:
    logging.critical(f"FALLO CRÍTICO AL IMPORTAR MSAL (después del diagnóstico): {type(e_msal).__name__}: {e_msal}. "
                     "La función no operará correctamente sin MSAL.", exc_info=True)
    # Si MSAL no se puede importar, define las excepciones como BaseException para evitar NameErrors posteriores,
    # aunque el código que las usa probablemente no se ejecute o falle.
    MsalUiRequiredException = BaseException
    MsalServiceError = BaseException
except Exception as e_msal_other:
    logging.critical(f"FALLO CRÍTICO - OTRA EXCEPCIÓN AL IMPORTAR MSAL: {type(e_msal_other).__name__}: {e_msal_other}.", exc_info=True)
    MsalUiRequiredException = BaseException
    MsalServiceError = BaseException
# --- Fin Importaciones MSAL Corregidas ---

# Importar constantes y el alias del ejecutor
try:
    from .shared.constants import GRAPH_API_DEFAULT_SCOPE, AZURE_OPENAI_DEFAULT_SCOPE, APP_NAME
    from .mapping_actions import available_actions
    from .ejecutor import execute_action as execute_action_func

    logger_name_init = f"{APP_NAME}.HttpTrigger"
    logger_init = logging.getLogger(logger_name_init)
    logger_init.info("Módulos base (.shared.constants, .mapping_actions, .ejecutor) importados correctamente.")

except ImportError as e_base:
    logger_init_fallback = logging.getLogger("EliteDynamicsPro.StartupErrorLogger")
    logger_init_fallback.critical(f"FALLO CRÍTICO AL IMPORTAR MODULOS BASE (__init__.py): {type(e_base).__name__}: {e_base}. "
                                  "La función no operará correctamente.", exc_info=True)
    available_actions = {} 
    def dummy_execute_action_on_base_import_error(action_name, parametros, headers, actions_map):
        logging.error("EJECUTOR DUMMY (desde __init__): Llamado debido a fallo crítico en importación de módulos base (mapping/ejecutor).")
        return {"status": "error", "message": "Error crítico de configuración interna del servidor (fallo de importación de módulos base)."}
    execute_action_func = dummy_execute_action_on_base_import_error
    logger_init = logger_init_fallback # Usar el logger de fallback
    APP_NAME = "EliteDynamicsPro_Fallback" # Definir APP_NAME para que el logger en main() no falle

except Exception as e_base_other:
    logger_init_fallback = logging.getLogger("EliteDynamicsPro.StartupCriticalExceptionLogger")
    logger_init_fallback.critical(f"EXCEPCIÓN INESPERADA CRÍTICA durante importaciones base en MyHttpTrigger/__init__.py: {e_base_other}", exc_info=True)
    available_actions = {}
    def dummy_execute_action_on_startup_exception(action_name, parametros, headers, actions_map):
        logging.error("EJECUTOR DUMMY (desde __init__): Llamado debido a excepción crítica en carga de módulos.")
        return {"status": "error", "message": "Error crítico de configuración interna del servidor (excepción en carga de módulos)."}
    execute_action_func = dummy_execute_action_on_startup_exception
    logger_init = logger_init_fallback
    APP_NAME = "EliteDynamicsPro_Fallback"

def main(req: func.HttpRequest) -> func.HttpResponse:
    global logger_init # Asegurar que usamos el logger_init global que podría ser el de fallback
    
    # Re-asegurar que logger_init tiene un nombre razonable si las importaciones iniciales fallaron
    if not hasattr(logger_init, 'name') or "Fallback" in logger_init.name or "StartupErrorLogger" in logger_init.name:
        try: current_app_name = APP_NAME
        except NameError: current_app_name = "EliteDynamicsPro_MainFallback" # Un nombre por si APP_NAME tampoco está
        logger_main = logging.getLogger(f"{current_app_name}.HttpTrigger.main")
    else:
        logger_main = logger_init # Usar el logger_init si se inicializó correctamente

    request_id = req.headers.get("X-Request-ID", os.urandom(8).hex())
    logger_main.info(f"Python HTTP trigger procesando petición. RequestId: {request_id}, URL: {req.url}, Method: {req.method}")

    if 'MsalUiRequiredException' not in globals() or 'MsalServiceError' not in globals():
        logger_main.critical(f"RequestId: {request_id} - MSAL o sus excepciones no se importaron. La función no puede operar.")
        return func.HttpResponse(json.dumps({"error": "Error interno servidor", "message": "Dependencia MSAL crítica no cargada."}), status_code=500, mimetype="application/json")

    if not available_actions or not callable(execute_action_func) or execute_action_func.__name__.startswith("dummy_execute"):
        logger_main.critical(f"RequestId: {request_id} - Error Crítico: Módulos/Ejecutor no disponibles o dummies. Revisar logs de inicio.")
        return func.HttpResponse(json.dumps({"error": "Error interno servidor", "message": "Componentes críticos no cargados."}), status_code=500, mimetype="application/json")
    logger_main.info(f"RequestId: {request_id} - Módulos cargados. Acciones: {list(available_actions.keys()) if available_actions else 'NINGUNA'}")

    auth_header = req.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        logger_main.warning(f"RequestId: {request_id} - Falta token Bearer.")
        return func.HttpResponse(json.dumps({"error": "Unauthorized", "message": "Token Bearer requerido."}), status_code=401, mimetype="application/json")
    user_assertion_token = auth_header.split(' ')[1]

    try:
        req_body = req.get_json(); action_name = req_body.get('action'); action_params = req_body.get('params', {})
        target_service_for_obo = req_body.get('target_service', 'graph').lower()
        if not action_name: 
            logger_main.warning(f"RequestId: {request_id} - Solicitud inválida: 'action' requerido.")
            return func.HttpResponse(json.dumps({"error": "Solicitud inválida", "message": "'action' requerido."}), status_code=400, mimetype="application/json")
        if not isinstance(action_params, dict): 
            logger_main.warning(f"RequestId: {request_id} - Solicitud inválida: 'params' debe ser un objeto.")
            return func.HttpResponse(json.dumps({"error": "Solicitud inválida", "message": "'params' debe ser un objeto."}), status_code=400, mimetype="application/json")
    except ValueError as e:
        logger_main.warning(f"RequestId: {request_id} - Error parseando JSON: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Solicitud inválida", "message": f"Cuerpo JSON malformado: {e}"}), status_code=400, mimetype="application/json")

    final_auth_token_for_action = None
    try:
        client_id = os.environ["CLIENT_ID"]; client_secret = os.environ["CLIENT_SECRET"]; tenant_id = os.environ["TENANT_ID"]
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        
        # Usar GRAPH_API_DEFAULT_SCOPE y AZURE_OPENAI_DEFAULT_SCOPE importados
        if target_service_for_obo == 'openai': current_obo_scope = AZURE_OPENAI_DEFAULT_SCOPE
        elif target_service_for_obo == 'graph': current_obo_scope = GRAPH_API_DEFAULT_SCOPE
        else: current_obo_scope = GRAPH_API_DEFAULT_SCOPE; logger_main.warning(f"Target service '{target_service_for_obo}' no reconocido, usando scope Graph.")
        
        logger_main.info(f"RequestId: {request_id} - Intentando OBO para target '{target_service_for_obo}' scope: {current_obo_scope}")
        cca = ConfidentialClientApplication(client_id, authority=authority, client_credential=client_secret)
        result = cca.acquire_token_on_behalf_of(user_assertion=user_assertion_token, scopes=current_obo_scope)

        if "access_token" in result: final_auth_token_for_action = result['access_token']; logger_main.info(f"RequestId: {request_id} - Token OBO adquirido.")
        elif "error" in result:
            err_code=result.get('error'); err_desc=result.get('error_description','N/A'); sub_err=result.get('suberror')
            logger_main.error(f"RequestId: {request_id} - Error MSAL OBO: Code='{err_code}', SubErr='{sub_err}', Desc='{err_desc}'")
            http_status=403; msg=f"Fallo OBO ({err_code})."
            if "AADSTS50027" in err_desc or "invalid_grant" in err_code: http_status=401; msg="Token usuario inválido/expirado."
            elif "AADSTS65001" in err_desc: msg="Consentimiento requerido."
            return func.HttpResponse(json.dumps({"error": "Fallo OBO", "message": msg, "details": err_desc}), status_code=http_status, mimetype="application/json")
        else:
            logger_main.error(f"RequestId: {request_id} - Respuesta MSAL OBO inesperada: {result}")
            return func.HttpResponse(json.dumps({"error": "Fallo OBO", "message": "Respuesta auth inesperada."}), status_code=500, mimetype="application/json")

    except MsalUiRequiredException as e: 
        logger_main.error(f"RequestId: {request_id} - Error MSAL OBO (Consentimiento/Interacción): {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Consentimiento Requerido", "message": "Permisos o interacción requerida.", "details": str(e)}), status_code=403, mimetype="application/json")
    except MsalServiceError as e: 
        logger_main.error(f"RequestId: {request_id} - Error MSAL OBO (Servicio): {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Error Servicio Auth", "message": "Error en servicio de autenticación.", "details": str(e)}), status_code=500, mimetype="application/json")
    except KeyError as e: 
        logger_main.critical(f"RequestId: {request_id} - Falta variable de entorno para OBO: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Error Configuración Servidor", "message": f"Variable '{e}' no configurada."}), status_code=500, mimetype="application/json")
    except Exception as e: 
        logger_main.critical(f"RequestId: {request_id} - Excepción general OBO: {type(e).__name__} - {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Error Interno Auth", "message": "Excepción durante OBO."}), status_code=500, mimetype="application/json")

    if not final_auth_token_for_action:
        logger_main.critical(f"RequestId: {request_id} - Token OBO final es None después del bloque try-except.")
        return func.HttpResponse(json.dumps({"error": "Error Interno Crítico", "message": "Falló obtención token (post-exception check)."}), status_code=500, mimetype="application/json")

    action_headers = {'Authorization': f'Bearer {final_auth_token_for_action}', 'Content-Type': 'application/json'}
    logger_main.info(f"RequestId: {request_id} - Llamando ejecutor para acción: '{action_name}'")
    action_result = execute_action_func(action_name, action_params, action_headers, available_actions)

    response_status_code = 500 
    if isinstance(action_result, dict):
        action_status = action_result.get("status", "undefined")
        if "success" in action_status: response_status_code = 200
        elif action_status == "error" and "Acción no encontrada" in action_result.get("message", ""): response_status_code = 404
    logger_main.info(f"RequestId: {request_id} - Acción '{action_name}' completada. Devolviendo HTTP {response_status_code}.")
    return func.HttpResponse(json.dumps(action_result), status_code=response_status_code, mimetype="application/json")