# MyHttpTrigger/__init__.py (NUEVO ENFOQUE CON DEFAULTAZURECREDENTIAL)
import logging
import azure.functions as func
import os
import json
import sys # Lo mantenemos por si acaso, aunque no lo usemos directamente en este snippet

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
        logging.error("EJECUTOR DUMMY (desde __init__): Llamado debido a fallo crítico en importación de módulos base (mapping/ejecutor).")
        return {"status": "error", "message": "Error crítico de configuración interna del servidor (fallo de importación de módulos base)."}
    execute_action_func = dummy_execute_action_on_base_import_error
    APP_NAME = "EliteDynamicsPro_Fallback_InitError" # Definir para que logger_main no falle
except Exception as e:
    logger_init = logging.getLogger("EliteDynamicsPro.StartupCriticalExceptionLogger")
    logger_init.critical(f"EXCEPCIÓN INESPERADA CRÍTICA durante importaciones en MyHttpTrigger/__init__.py: {e}", exc_info=True)
    available_actions = {}
    def dummy_execute_action_on_startup_exception(action_name, parametros, headers, actions_map):
        logging.error("EJECUTOR DUMMY (desde __init__): Llamado debido a excepción crítica en carga de módulos.")
        return {"status": "error", "message": "Error crítico de configuración interna del servidor (excepción en carga de módulos)."}
    execute_action_func = dummy_execute_action_on_startup_exception
    APP_NAME = "EliteDynamicsPro_Fallback_InitException" # Definir para que logger_main no falle

# --- FIN IMPORTACIONES ORIGINALES ---

# Convertimos 'main' en una función asíncrona para usar 'await' con DefaultAzureCredential
async def main(req: func.HttpRequest) -> func.HttpResponse:
    # Usar el logger_init global o un fallback si falló la inicialización
    global logger_init 
    logger_main = logger_init
    try:
        # Si logger_init no se pudo crear con APP_NAME, intentamos obtener APP_NAME ahora o usamos un fallback
        if APP_NAME not in logger_init.name: # Una forma de verificar si se usó un nombre de fallback
            current_app_name_for_logger = APP_NAME
    except NameError: # Si APP_NAME tampoco está definido
        current_app_name_for_logger = "EliteDynamicsPro_MainFallback"
    if logger_init.name.startswith("EliteDynamicsPro.Startup"): # Si usamos uno de los loggers de error de inicio
         logger_main = logging.getLogger(f"{current_app_name_for_logger}.HttpTrigger.main")


    request_id = req.headers.get("X-Request-ID", os.urandom(8).hex())
    logger_main.info(f"Python HTTP trigger (DefaultAzureCredential) procesando petición. RequestId: {request_id}, URL: {req.url}, Method: {req.method}")

    # 1. Validar carga de componentes críticos (esto no cambia)
    if not available_actions or not callable(execute_action_func) or execute_action_func.__name__.startswith("dummy_execute"):
        logger_main.critical(f"RequestId: {request_id} - Error Crítico: Módulos/Ejecutor no disponibles o dummies. Revisar logs de inicio.")
        return func.HttpResponse(json.dumps({"error": "Error interno servidor", "message": "Componentes críticos no cargados."}), status_code=500, mimetype="application/json")
    logger_main.info(f"RequestId: {request_id} - Módulos cargados. Acciones: {list(available_actions.keys()) if available_actions else 'NINGUNA'}")

    # 2. Obtener token de usuario (si todavía lo necesitas para identificar al usuario o lógica de negocio)
    # Este token ya NO se usará para el flujo OBO.
    user_auth_header = req.headers.get('Authorization')
    user_principal_name = "desconocido" # Valor por defecto
    if user_auth_header and user_auth_header.startswith('Bearer '):
        user_token_for_info = user_auth_header.split(' ')[1]
        # Aquí podrías decodificar user_token_for_info si necesitas el UPN del usuario para tu lógica,
        # pero NO lo usaremos para autenticar la llamada a Graph.
        # Por ahora, solo lo registramos si existe.
        logger_main.info(f"RequestId: {request_id} - Se recibió un token Bearer de usuario (solo para información, no para OBO).")
        # Ejemplo de cómo podrías obtener el UPN si decodificas el token (requiere PyJWT y conocer las claves públicas de AAD)
        # try:
        #     decoded_token = jwt.decode(user_token_for_info, algorithms=["RS256"], options={"verify_signature": False}) # Simplificado, ¡NO USAR EN PRODUCCIÓN SIN VERIFICACIÓN DE FIRMA!
        #     user_principal_name = decoded_token.get("upn", "upn_no_encontrado")
        #     logger_main.info(f"RequestId: {request_id} - UPN del token de usuario (informativo): {user_principal_name}")
        # except Exception as e_jwt:
        #     logger_main.warning(f"RequestId: {request_id} - No se pudo decodificar el token de usuario para info: {e_jwt}")
    else:
        logger_main.warning(f"RequestId: {request_id} - No se recibió token Bearer de usuario. La función actuará con su propia identidad.")


    # 3. Procesar cuerpo JSON (esto no cambia)
    try:
        req_body = req.get_json(); action_name = req_body.get('action'); action_params = req_body.get('params', {})
        target_service_for_obo = req_body.get('target_service', 'graph').lower() # Mantenemos esta variable por ahora si tu lógica la usa para diferenciar targets
        if not action_name: return func.HttpResponse(json.dumps({"error": "Solicitud inválida", "message": "'action' requerido."}), status_code=400, mimetype="application/json")
        if not isinstance(action_params, dict): return func.HttpResponse(json.dumps({"error": "Solicitud inválida", "message": "'params' debe ser un objeto."}), status_code=400, mimetype="application/json")
    except ValueError as e:
        logger_main.warning(f"RequestId: {request_id} - Error parseando JSON: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Solicitud inválida", "message": f"Cuerpo JSON malformado: {e}"}), status_code=400, mimetype="application/json")

    # 4. Lógica de Obtención de Token con DefaultAzureCredential (NUEVA SECCIÓN)
    final_auth_token_for_action = None
    try:
        logger_main.info(f"RequestId: {request_id} - Intentando obtener token para servicio '{target_service_for_obo}' usando DefaultAzureCredential.")
        
        credential = DefaultAzureCredential()
        
        # Determinar el scope para el token.
        # Para Microsoft Graph con permisos de aplicación, el scope es "https://graph.microsoft.com/.default"
        # Para otros servicios de Azure protegidos por AAD (como Azure OpenAI si está configurado así),
        # sería la URI del ID de Aplicación del recurso seguido de "/.default".
        
        current_service_scope = ""
        if target_service_for_obo == 'graph':
            current_service_scope = "https://graph.microsoft.com/.default"
        elif target_service_for_obo == 'openai':
            # ¡IMPORTANTE! Necesitas el scope correcto para tu servicio Azure OpenAI.
            # Si tu AZURE_OPENAI_DEFAULT_SCOPE era ['https://cognitiveservices.azure.com/user_impersonation']
            # para DefaultAzureCredential con Managed Identity necesitas el scope de recurso:
            # "https://cognitiveservices.azure.com/.default"
            # O si es una API personalizada, su "Application ID URI" + "/.default"
            # Revisa la documentación de autenticación de tu recurso OpenAI específico.
            # Por ahora, usaré un placeholder que DEBES revisar y ajustar.
            openai_resource_id_or_uri = os.environ.get("AZURE_OPENAI_RESOURCE_ID_FOR_AUTH") # Ej: "https://<tu-nombre-openai>.openai.azure.com"
            if openai_resource_id_or_uri:
                 current_service_scope = f"{openai_resource_id_or_uri}/.default"
            else:
                 logger_main.error(f"RequestId: {request_id} - Variable de entorno AZURE_OPENAI_RESOURCE_ID_FOR_AUTH no configurada para obtener token de OpenAI.")
                 # Decide si quieres fallar o usar Graph como fallback
                 # current_service_scope = "https://graph.microsoft.com/.default" # Fallback a Graph si OpenAI no está configurado
                 # logger_main.warning(f"RequestId: {request_id} - Usando Graph scope como fallback para OpenAI no configurado.")
                 # O fallar:
                 return func.HttpResponse(json.dumps({"error": "Configuración Inválida", "message": "Scope de OpenAI no configurado (AZURE_OPENAI_RESOURCE_ID_FOR_AUTH)."}), status_code=500, mimetype="application/json")
            
            logger_main.info(f"RequestId: {request_id} - Scope para OpenAI determinado como: {current_service_scope}")
        else:
            logger_main.warning(f"RequestId: {request_id} - Target service '{target_service_for_obo}' no reconocido, usando Graph por defecto.")
            current_service_scope = "https://graph.microsoft.com/.default"

        if not current_service_scope:
             logger_main.error(f"RequestId: {request_id} - No se pudo determinar un scope válido para DefaultAzureCredential para el target service: {target_service_for_obo}")
             return func.HttpResponse(json.dumps({"error": "Configuración Inválida", "message": f"Scope no configurado/válido para el servicio '{target_service_for_obo}'."}), status_code=500, mimetype="application/json")

        # Obtener el token de forma asíncrona
        token_result = await credential.get_token(current_service_scope) # LLAMADA ASÍNCRONA
        
        final_auth_token_for_action = token_result.token
        logger_main.info(f"RequestId: {request_id} - Token para scope '{current_service_scope}' adquirido exitosamente con DefaultAzureCredential.")

    except ClientAuthenticationError as e_auth:
        logger_main.critical(f"RequestId: {request_id} - Fallo de autenticación con DefaultAzureCredential para scope '{current_service_scope}': {e_auth}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Fallo de Autenticación de Servicio", "message": "No se pudo autenticar la función para acceder al recurso.", "details": str(e_auth)}), status_code=500, mimetype="application/json")
    except Exception as e_token:
        logger_main.critical(f"RequestId: {request_id} - Excepción general obteniendo token con DefaultAzureCredential para scope '{current_service_scope}': {type(e_token).__name__} - {e_token}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": "Error Interno de Autenticación", "message": "Excepción durante la obtención del token de servicio."}), status_code=500, mimetype="application/json")

    if not final_auth_token_for_action:
        logger_main.critical(f"RequestId: {request_id} - Token final es None después de DefaultAzureCredential. Esto no debería ocurrir si no hubo excepción.")
        return func.HttpResponse(json.dumps({"error": "Error Interno Crítico", "message": "Falló la obtención del token de servicio (inesperado)."}), status_code=500, mimetype="application/json")

    # 5. Preparar cabeceras y ejecutar acción (esto no cambia)
    action_headers = {'Authorization': f'Bearer {final_auth_token_for_action}', 'Content-Type': 'application/json'}
    logger_main.info(f"RequestId: {request_id} - Llamando ejecutor para acción: '{action_name}' con token de Identidad Administrada.")
    
    # Si execute_action_func o las acciones que llama hacen I/O, deberían ser async y usar await aquí.
    # Por ahora, lo dejamos como síncrono. Si falla, necesitaremos refactorizar execute_action_func a async.
    try:
        if execute_action_func.__name__.startswith("dummy_execute"): # Ya se validó antes pero doble chequeo
             logger_main.error(f"RequestId: {request_id} - Intento de llamar a un ejecutor dummy en main.")
             action_result = {"status": "error", "message": "Componentes críticos (ejecutor) no cargados."}
        else:
             # Si execute_action_func es una función regular (no async)
             action_result = execute_action_func(action_name, action_params, action_headers, available_actions)
             # Si execute_action_func fuera async:
             # action_result = await execute_action_func(action_name, action_params, action_headers, available_actions)
    except Exception as e_exec:
        logger_main.error(f"RequestId: {request_id} - Excepción durante la ejecución de la acción '{action_name}': {e_exec}", exc_info=True)
        action_result = {"status": "error", "message": f"Error al ejecutar la acción: {e_exec}"}


    # 6. Devolver resultado (esto no cambia)
    response_status_code = 500 
    if isinstance(action_result, dict):
        action_status = action_result.get("status", "undefined")
        if "success" in action_status: response_status_code = 200
        elif action_status == "error" and "Acción no encontrada" in action_result.get("message", ""): response_status_code = 404
    logger_main.info(f"RequestId: {request_id} - Acción '{action_name}' completada. Devolviendo HTTP {response_status_code}.")
    return func.HttpResponse(json.dumps(action_result), status_code=response_status_code, mimetype="application/json")