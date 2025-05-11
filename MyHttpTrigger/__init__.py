# MyHttpTrigger/__init__.py (NUEVO ENFOQUE CON DEFAULTAZURECREDENTIAL)
import logging
import azure.functions as func
import os
import json
import sys 

# --- NUEVAS IMPORTACIONES PARA DEFAULTAZURECREDENTIAL ---
from azure.identity import DefaultAzureCredential
from azure.core.exceptions import ClientAuthenticationError 
# --- FIN NUEVAS IMPORTACIONES ---

# --- IMPORTACIONES ORIGINALES (MANTENEMOS LAS QUE NECESITAS) ---
# Ya no necesitamos MsalUiRequiredException ni MsalServiceError directamente de msal
try:
    from .shared.constants import GRAPH_API_DEFAULT_SCOPE, AZURE_OPENAI_DEFAULT_SCOPE, APP_NAME
    from .mapping_actions import available_actions
    from .ejecutor import execute_action as execute_action_func

    logger_name_init = f"{APP_NAME}.HttpTrigger"
    logger_init = logging.getLogger(logger_name_init)
    logger_init.info(f"Módulos base (.shared.constants, .mapping_actions, .ejecutor) importados correctamente para {APP_NAME}.")

except ImportError as e:
    logger_init = logging.getLogger("EliteDynamicsPro.StartupErrorLogger")
    logger_init.critical(f"FALLO CRÍTICO AL IMPORTAR MODULOS BASE (__init__.py): {type(e).__name__}: {e}. "
                     "La función no operará correctamente.", exc_info=True)
    available_actions = {} 
    def dummy_execute_action_on_base_import_error(action_name, parametros, headers, actions_map):
        logging.error("EJECUTOR DUMMY (desde __init__): Llamado debido a fallo crítico en importación de módulos base.")
        return {"status": "error", "message": "Error crítico de configuración interna del servidor (fallo de importación de módulos base)."}
    execute_action_func = dummy_execute_action_on_base_import_error
    APP_NAME = "EliteDynamicsPro_Fallback_InitError" 
except Exception as e:
    logger_init = logging.getLogger("EliteDynamicsPro.StartupCriticalExceptionLogger")
    logger_init.critical(f"EXCEPCIÓN INESPERADA CRÍTICA durante importaciones en MyHttpTrigger/__init__.py: {e}", exc_info=True)
    available_actions = {}
    def dummy_execute_action_on_startup_exception(action_name, parametros, headers, actions_map):
        logging.error("EJECUTOR DUMMY (desde __init__): Llamado debido a excepción crítica en carga de módulos.")
        return {"status": "error", "message": "Error crítico de configuración interna del servidor (excepción en carga de módulos)."}
    execute_action_func = dummy_execute_action_on_startup_exception
    APP_NAME = "EliteDynamicsPro_Fallback_InitException"
# --- FIN IMPORTACIONES ORIGINALES ---

# Convertimos 'main' en una función asíncrona para usar 'await' con DefaultAzureCredential
async def main(req: func.HttpRequest) -> func.HttpResponse:
    global logger_init 
    logger_main = logger_init
    try:
        # Si logger_init no se pudo crear con APP_NAME, intentamos obtener APP_NAME ahora o usamos un fallback
        if APP_NAME not in logger_init.name: 
            current_app_name_for_logger = APP_NAME
    except NameError: 
        current_app_name_for_logger = "EliteDynamicsPro_MainFallback"
    if logger_init.name.startswith("EliteDynamicsPro.Startup"):
         logger_main = logging.getLogger(f"{current_app_name_for_logger}.HttpTrigger.main")


    request_id = req.headers.get("X-Request-ID", os.urandom(8).hex())
    logger_main.info(f"Python HTTP trigger (DefaultAzureCredential) procesando petición. RequestId: {request_id}, URL: {req.url}, Method: {req.method}")

    if not available_actions or not callable(execute_action_func) or execute_action_func.__name__.startswith("dummy_execute"):
        logger_main.critical(f"RequestId: {request_id} - Error Crítico: Módulos/Ejecutor no disponibles o dummies.")
        return func.HttpResponse(json.dumps({"error": "Error interno servidor", "message": "Componentes críticos no cargados."}), status_code=500, mimetype="application/json")
    logger_main.info(f"RequestId: {request_id} - Módulos cargados. Acciones: {list(available_actions.keys()) if available_actions else 'NINGUNA'}")

    user_auth_header = req.headers.get('Authorization')
    if user_auth_header and user_auth_header.startswith('Bearer '):
        logger_main.info(f"RequestId: {request_id} - Se recibió un token Bearer de usuario (solo para información).")
    else:
        logger_main.warning(f"RequestId: {request_id} - No se recibió token Bearer de usuario. La función actuará con su propia identidad.")

    try:
        req_body = req.get_json(); action_name = req_body.get('action'); action_params = req_body.get('params', {})
        target_service = req_body.get('target_service', 'graph').lower() 
        if not action_name: return func.HttpResponse(json.dumps({"error": "Solicitud inválida", "message": "'action' requerido."}), status_code=400, mimetype="application/json")
        if not isinstance(action_params, dict): return func.HttpResponse(json.dumps({"error": "Solicitud inválida", "message": "'params' debe ser un objeto."}), status_code=400, mimetype="application/json")
    except ValueError as e:
        logger_main.warning(f"RequestId: {request_id} - Error parseando JSON: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Solicitud inválida", "message": f"Cuerpo JSON malformado: {e}"}), status_code=400, mimetype="application/json")

    final_auth_token_for_action = None
    try:
        logger_main.info(f"RequestId: {request_id} - Intentando obtener token para servicio '{target_service}' usando DefaultAzureCredential.")
        credential = DefaultAzureCredential()
        current_service_scope = ""

        if target_service == 'graph':
            current_service_scope = "https://graph.microsoft.com/.default"
        elif target_service == 'openai':
            # ¡IMPORTANTE! Necesitas el scope correcto para tu servicio Azure OpenAI.
            # Si tu AZURE_OPENAI_DEFAULT_SCOPE era ['https://cognitiveservices.azure.com/user_impersonation']
            # para DefaultAzureCredential con Managed Identity necesitas el scope de recurso:
            # "https://cognitiveservices.azure.com/.default"
            # O si es una API personalizada, su "Application ID URI" + "/.default"
            # Revisa la documentación de autenticación de tu recurso OpenAI específico.
            # Te recomiendo crear una variable de entorno como AZURE_OPENAI_RESOURCE_ENDPOINT para esto.
            openai_resource_endpoint = os.environ.get("AZURE_OPENAI_RESOURCE_ENDPOINT") # Ej: "https://<tu-nombre-openai>.openai.azure.com"
            if openai_resource_endpoint:
                 current_service_scope = f"{openai_resource_endpoint}/.default"
            else:
                 logger_main.error(f"RequestId: {request_id} - Variable de entorno AZURE_OPENAI_RESOURCE_ENDPOINT no configurada para obtener token de OpenAI.")
                 return func.HttpResponse(json.dumps({"error": "Configuración Inválida", "message": "Scope de OpenAI no configurado (AZURE_OPENAI_RESOURCE_ENDPOINT)."}), status_code=500, mimetype="application/json")
            logger_main.info(f"RequestId: {request_id} - Scope para OpenAI determinado como: {current_service_scope}")
        else:
            logger_main.warning(f"RequestId: {request_id} - Target service '{target_service}' no reconocido, usando Graph por defecto.")
            current_service_scope = "https://graph.microsoft.com/.default"

        if not current_service_scope: # Doble chequeo por si acaso
             logger_main.error(f"RequestId: {request_id} - Scope no determinado para '{target_service}'.")
             return func.HttpResponse(json.dumps({"error": "Configuración Inválida", "message": f"Scope no válido para servicio '{target_service}'."}), status_code=500, mimetype="application/json")
        
        token_result = await credential.get_token(current_service_scope) # LLAMADA ASÍNCRONA
        final_auth_token_for_action = token_result.token
        logger_main.info(f"RequestId: {request_id} - Token para '{current_service_scope}' adquirido con DefaultAzureCredential.")

    except ClientAuthenticationError as e_auth:
        logger_main.critical(f"RequestId: {request_id} - Fallo de autenticación con DefaultAzureCredential para '{current_service_scope}': {e_auth}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Fallo de Autenticación de Servicio", "message": "No se pudo autenticar la función para acceder al recurso.", "details": str(e_auth)}), status_code=500, mimetype="application/json")
    except Exception as e_token:
        logger_main.critical(f"RequestId: {request_id} - Excepción obteniendo token para '{current_service_scope}': {type(e_token).__name__} - {e_token}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Error Interno de Autenticación", "message": "Excepción durante obtención de token."}), status_code=500, mimetype="application/json")

    if not final_auth_token_for_action:
        logger_main.critical(f"RequestId: {request_id} - Token final es None (inesperado).")
        return func.HttpResponse(json.dumps({"error": "Error Interno Crítico", "message": "Falló obtención de token."}), status_code=500, mimetype="application/json")

    action_headers = {'Authorization': f'Bearer {final_auth_token_for_action}', 'Content-Type': 'application/json'}
    logger_main.info(f"RequestId: {request_id} - Llamando ejecutor para acción: '{action_name}'.")
    
    try:
        if execute_action_func.__name__.startswith("dummy_execute"):
             action_result = {"status": "error", "message": "Componentes críticos (ejecutor) no cargados."}
        else:
             # Si execute_action_func NO es async, esta llamada está bien.
             # Si execute_action_func SÍ es async, necesitarías: await execute_action_func(...)
             action_result = execute_action_func(action_name, action_params, action_headers, available_actions)
    except Exception as e_exec:
        logger_main.error(f"RequestId: {request_id} - Excepción durante ejecución de acción '{action_name}': {e_exec}", exc_info=True)
        action_result = {"status": "error", "message": f"Error al ejecutar la acción: {e_exec}"}

    response_status_code = 500 
    if isinstance(action_result, dict):
        action_status = action_result.get("status", "undefined")
        if "success" in action_status: response_status_code = 200
        elif action_status == "error" and "Acción no encontrada" in action_result.get("message", ""): response_status_code = 404
    logger_main.info(f"RequestId: {request_id} - Acción '{action_name}' completada. Devolviendo HTTP {response_status_code}.")
    return func.HttpResponse(json.dumps(action_result), status_code=response_status_code, mimetype="application/json")