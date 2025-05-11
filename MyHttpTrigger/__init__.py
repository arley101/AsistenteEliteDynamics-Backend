# MyHttpTrigger/__init__.py (CON DIAGNÓSTICO MEJORADO Y COMPLETO)
import logging
import azure.functions as func
import os
import json
import sys # Asegurarse de que sys está importado para el diagnóstico

# --- Inicio de código de depuración (MODIFICADO A NIVEL ERROR/CRITICAL) ---
def log_environment_details():
    logging.error("--- Environment Diagnostic Start (FORCED ERROR LEVEL) ---")
    logging.error(f"Python version: {sys.version}")
    logging.error(f"sys.path: {sys.path}")
    
    pythonpath_env = os.environ.get('PYTHONPATH')
    logging.error(f"PYTHONPATH environment variable: {pythonpath_env if pythonpath_env else 'Not set'}")
    
    current_working_dir = os.getcwd()
    logging.error(f"Current working directory: {current_working_dir}")
    
    wwwroot_path = '/home/site/wwwroot' # Ruta estándar en App Service Linux
    if os.path.exists(wwwroot_path):
        logging.error(f"Contents of {wwwroot_path} (first 20 items): {os.listdir(wwwroot_path)[:20]}")
    else:
        logging.error(f"{wwwroot_path} not found.")
        
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
            logging.error(f"Found potential site-packages: {path_to_check}")
            logging.error(f"Contents of {path_to_check} (first 20 items): {os.listdir(path_to_check)[:20]}")
            msal_package_path = os.path.join(path_to_check, 'msal')
            if os.path.exists(msal_package_path):
                logging.error(f"MSAL directory FOUND at: {msal_package_path}")
                logging.error(f"Contents of msal directory (first 10 items): {os.listdir(msal_package_path)[:10]}")
                msal_found_in_any_path = True
            else:
                # Usamos warning aquí porque el path existe pero msal no está dentro.
                logging.warning(f"MSAL directory NOT FOUND at: {msal_package_path} (path checked: {path_to_check})")
        else:
            logging.error(f"Potential site-packages path does not exist: {path_to_check}")
    
    if not msal_found_in_any_path:
        logging.critical("MSAL package directory was NOT FOUND in any of the checked standard paths (FORCED CRITICAL).")
        
    logging.error("--- Environment Diagnostic End (FORCED ERROR LEVEL) ---")

# Llamar a la función de diagnóstico al inicio del script del worker de Python
log_environment_details()
# --- Fin de código de depuración ---

# --- Importaciones MSAL (MODIFICADO MENSAJE DE ÉXITO A NIVEL ERROR) ---
# Intentaremos importar MSAL DESPUÉS del diagnóstico.
try:
    from msal import ConfidentialClientApplication
    # Importar TODAS las excepciones MSAL específicas desde msal.exceptions
    from msal.exceptions import MsalUiRequiredException, MsalServiceError
    # Si la importación es exitosa, logueamos a nivel ERROR para que sea visible
    logging.error("MSAL y excepciones MSAL importadas correctamente después del diagnóstico (FORCED ERROR LEVEL).")
except ModuleNotFoundError as e_msal:
    logging.critical(f"FALLO CRÍTICO AL IMPORTAR MSAL (después del diagnóstico): {type(e_msal).__name__}: {e_msal}. "
                     "La función no operará correctamente sin MSAL.", exc_info=True)
    # Definir dummies para evitar NameErrors si el resto del código intenta usarlas (aunque probablemente no debería llegar allí)
    MsalUiRequiredException = BaseException 
    MsalServiceError = BaseException
except Exception as e_msal_other: # Capturar cualquier otra excepción durante la importación de MSAL
    logging.critical(f"FALLO CRÍTICO - OTRA EXCEPCIÓN AL IMPORTAR MSAL (después del diagnóstico): {type(e_msal_other).__name__}: {e_msal_other}.", exc_info=True)
    MsalUiRequiredException = BaseException
    MsalServiceError = BaseException
# --- Fin Importaciones MSAL ---

# Importar constantes y el alias del ejecutor
try:
    # Asume que estos módulos existen en las rutas correctas ahora
    from .shared.constants import GRAPH_API_DEFAULT_SCOPE, AZURE_OPENAI_DEFAULT_SCOPE, APP_NAME
    from .mapping_actions import available_actions
    from .ejecutor import execute_action as execute_action_func

    # Definir logger_init aquí si las importaciones básicas funcionan
    logger_name_init = f"{APP_NAME}.HttpTrigger"
    logger_init = logging.getLogger(logger_name_init)
    # Loguear éxito de importaciones base (usando el logger recién definido)
    logger_init.info("Módulos base (.shared.constants, .mapping_actions, .ejecutor) importados correctamente.")


except ImportError as e:
    # Si las importaciones iniciales fallan, usa un logger de fallback
    # Esto es crucial si, por ejemplo, constants.py tiene un error.
    logger_init = logging.getLogger("EliteDynamicsPro.StartupErrorLogger") # logger_init se asigna aquí
    logger_init.critical(f"FALLO CRÍTICO AL IMPORTAR MODULOS BASE (__init__.py): {type(e).__name__}: {e}. "
                     "La función no operará correctamente.", exc_info=True)
    available_actions = {} # Define como vacío para evitar NameError
    # Define una función dummy para que la llamada a execute_action_func no falle por NameError
    def dummy_execute_action_on_base_import_error(action_name, parametros, headers, actions_map):
        logging.error("EJECUTOR DUMMY (desde __init__): Llamado debido a fallo crítico en importación de módulos base (mapping/ejecutor).")
        return {"status": "error", "message": "Error crítico de configuración interna del servidor (fallo de importación de módulos base)."}
    execute_action_func = dummy_execute_action_on_base_import_error
    APP_NAME = "EliteDynamicsPro_Fallback" # Definir un APP_NAME de fallback
except Exception as e_other_startup: # Renombrada la variable para evitar conflicto con 'e' de ImportError
    # Captura cualquier otra excepción inesperada durante la carga inicial
    logger_init = logging.getLogger("EliteDynamicsPro.StartupCriticalExceptionLogger") # logger_init se asigna aquí
    logger_init.critical(f"EXCEPCIÓN INESPERADA CRÍTICA durante importaciones en MyHttpTrigger/__init__.py: {e_other_startup}", exc_info=True)
    available_actions = {}
    def dummy_execute_action_on_startup_exception(action_name, parametros, headers, actions_map):
        logging.error("EJECUTOR DUMMY (desde __init__): Llamado debido a excepción crítica en carga de módulos.")
        return {"status": "error", "message": "Error crítico de configuración interna del servidor (excepción en carga de módulos)."}
    execute_action_func = dummy_execute_action_on_startup_exception
    APP_NAME = "EliteDynamicsPro_Fallback" # Definir un APP_NAME de fallback

def main(req: func.HttpRequest) -> func.HttpResponse:
    # Asegurar que el logger esté disponible, usando logger_init que se define en el scope global.
    # Si las importaciones iniciales fallaron, logger_init será uno de los loggers de fallback.
    global logger_init 
    # logger_main es ahora una referencia a logger_init o a una versión específica si logger_init es de fallback
    logger_main = logger_init 
    if "Fallback" in logger_main.name or "StartupErrorLogger" in logger_main.name or "StartupCriticalExceptionLogger" in logger_main.name:
        try:
            current_app_name = APP_NAME # APP_NAME debería estar definido incluso en los bloques except de fallback
        except NameError:
            current_app_name = "EliteDynamicsPro_Main_CriticalFallback" # Solo si APP_NAME no se definió
        logger_main = logging.getLogger(f"{current_app_name}.HttpTrigger.main")


    request_id = req.headers.get("X-Request-ID", os.urandom(8).hex())
    logger_main.info(f"Python HTTP trigger procesando petición. RequestId: {request_id}, URL: {req.url}, Method: {req.method}")

    # 1. Validar carga de MSAL (verificando si las excepciones MSAL fueron reemplazadas por BaseException)
    if 'MsalUiRequiredException' in globals() and MsalUiRequiredException == BaseException:
        logger_main.critical(f"RequestId: {request_id} - MSAL o sus excepciones no se importaron correctamente (son BaseException). La función no puede operar.")
        return func.HttpResponse(json.dumps({"error": "Error interno servidor", "message": "Dependencia MSAL crítica no cargada."}), status_code=500, mimetype="application/json")
    
    # Continuación de la validación de carga de componentes críticos
    if not available_actions or not callable(execute_action_func) or execute_action_func.__name__.startswith("dummy_execute"):
        logger_main.critical(f"RequestId: {request_id} - Error Crítico: Módulos/Ejecutor no disponibles o dummies. Revisar logs de inicio.")
        return func.HttpResponse(json.dumps({"error": "Error interno servidor", "message": "Componentes críticos no cargados."}), status_code=500, mimetype="application/json")
    logger_main.info(f"RequestId: {request_id} - Módulos cargados. Acciones: {list(available_actions.keys()) if available_actions else 'NINGUNA'}")

    # 2. Obtener token de usuario
    auth_header = req.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        logger_main.warning(f"RequestId: {request_id} - Falta token Bearer.")
        return func.HttpResponse(json.dumps({"error": "Unauthorized", "message": "Token Bearer requerido."}), status_code=401, mimetype="application/json")
    user_assertion_token = auth_header.split(' ')[1]

    # 3. Procesar cuerpo JSON
    try:
        req_body = req.get_json(); action_name = req_body.get('action'); action_params = req_body.get('params', {})
        target_service_for_obo = req_body.get('target_service', 'graph').lower()
        if not action_name: 
            logger_main.warning(f"RequestId: {request_id} - Solicitud inválida: 'action' requerido.") # Log añadido
            return func.HttpResponse(json.dumps({"error": "Solicitud inválida", "message": "'action' requerido."}), status_code=400, mimetype="application/json")
        if not isinstance(action_params, dict): 
            logger_main.warning(f"RequestId: {request_id} - Solicitud inválida: 'params' debe ser un objeto.") # Log añadido
            return func.HttpResponse(json.dumps({"error": "Solicitud inválida", "message": "'params' debe ser un objeto."}), status_code=400, mimetype="application/json")
    except ValueError as e_json_parse: # Renombrada la variable para evitar conflicto
        logger_main.warning(f"RequestId: {request_id} - Error parseando JSON: {e_json_parse}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Solicitud inválida", "message": f"Cuerpo JSON malformado: {e_json_parse}"}), status_code=400, mimetype="application/json")

    # 4. Lógica OBO
    final_auth_token_for_action = None
    try:
        client_id = os.environ["CLIENT_ID"]; client_secret = os.environ["CLIENT_SECRET"]; tenant_id = os.environ["TENANT_ID"]
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        
        # Usar constantes importadas (asumiendo que se cargaron)
        # Es importante que GRAPH_API_DEFAULT_SCOPE y AZURE_OPENAI_DEFAULT_SCOPE estén definidos
        # si este código se alcanza y las importaciones base fueron exitosas.
        if target_service_for_obo == 'openai': current_obo_scope = AZURE_OPENAI_DEFAULT_SCOPE
        elif target_service_for_obo == 'graph': current_obo_scope = GRAPH_API_DEFAULT_SCOPE
        else: current_obo_scope = GRAPH_API_DEFAULT_SCOPE; logger_main.warning(f"Target service '{target_service_for_obo}' no reconocido, usando scope Graph por defecto.")
        
        logger_main.info(f"RequestId: {request_id} - Intentando OBO para target '{target_service_for_obo}' scope: {current_obo_scope}")
        # Aquí es donde ConfidentialClientApplication se usa. Si no se importó, esto fallará.
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

    except MsalUiRequiredException as e_msal_ui: 
        logger_main.error(f"RequestId: {request_id} - Error MSAL OBO (Consentimiento/Interacción): {e_msal_ui}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Consentimiento Requerido", "message": "Permisos o interacción requerida.", "details": str(e_msal_ui)}), status_code=403, mimetype="application/json")
    except MsalServiceError as e_msal_service: 
        logger_main.error(f"RequestId: {request_id} - Error MSAL OBO (Servicio): {e_msal_service}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Error Servicio Auth", "message": "Error en servicio de autenticación.", "details": str(e_msal_service)}), status_code=500, mimetype="application/json")
    except KeyError as e_key_error: 
        logger_main.critical(f"RequestId: {request_id} - Falta variable de entorno para OBO: {e_key_error}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Error Configuración Servidor", "message": f"Variable '{e_key_error}' no configurada."}), status_code=500, mimetype="application/json")
    except Exception as e_obo_general: 
        logger_main.critical(f"RequestId: {request_id} - Excepción general OBO: {type(e_obo_general).__name__} - {e_obo_general}", exc_info=True)
        # Si es un NameError porque ConfidentialClientApplication no está definido (debido a fallo de importación de MSAL)
        if isinstance(e_obo_general, NameError) and "ConfidentialClientApplication" in str(e_obo_general):
             logger_main.critical(f"RequestId: {request_id} - NameError: ConfidentialClientApplication no está definido. MSAL no se importó.")
             return func.HttpResponse(json.dumps({"error": "Error Interno Crítico", "message": "Dependencia MSAL no disponible."}), status_code=500, mimetype="application/json")
        return func.HttpResponse(json.dumps({"error": "Error Interno Auth", "message": "Excepción durante OBO."}), status_code=500, mimetype="application/json")

    if not final_auth_token_for_action: # Esta verificación es importante
        logger_main.critical(f"RequestId: {request_id} - Token OBO final es None después del bloque try-except de OBO. Esto indica un fallo no capturado o una lógica incompleta.")
        return func.HttpResponse(json.dumps({"error": "Error Interno Crítico", "message": "Falló obtención token (post-exception check OBO)."}), status_code=500, mimetype="application/json")

    # 5. Preparar cabeceras y ejecutar acción
    action_headers = {'Authorization': f'Bearer {final_auth_token_for_action}', 'Content-Type': 'application/json'}
    logger_main.info(f"RequestId: {request_id} - Llamando ejecutor para acción: '{action_name}'")
    # execute_action_func podría ser el dummy si las importaciones base fallaron
    action_result = execute_action_func(action_name, action_params, action_headers, available_actions)

    # 6. Devolver resultado
    response_status_code = 500 # Default error
    if isinstance(action_result, dict):
        action_status = action_result.get("status", "undefined")
        if "success" in action_status: response_status_code = 200
        elif action_status == "error" and "Acción no encontrada" in action_result.get("message", ""): response_status_code = 404
        # Considerar otros códigos de estado basados en action_result si es necesario
    logger_main.info(f"RequestId: {request_id} - Acción '{action_name}' completada. Devolviendo HTTP {response_status_code}.")
    return func.HttpResponse(json.dumps(action_result), status_code=response_status_code, mimetype="application/json")