# MyHttpTrigger/__init__.py
import logging
import json
import azure.functions as func
from azure.identity import DefaultAzureCredential, CredentialUnavailableError
import os
import sys

# --- INICIO DEL AJUSTE DE SYS.PATH ---
# Añade la raíz del proyecto (/home/site/wwwroot en Azure) a sys.path
# Esto permite importaciones absolutas de módulos como 'shared', 'actions', 'mapping_actions', 'ejecutor'.
PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)
# --- FIN DEL AJUSTE DE SYS.PATH ---

# Ahora se pueden importar los módulos de la raíz del proyecto
# (ejecutor.py, mapping_actions.py, shared/, actions/)
import ejecutor # ejecutor.py está en la raíz
import mapping_actions # mapping_actions.py está en la raíz
from shared import constants
from shared.helpers.http_client import AuthenticatedHttpClient

logger = logging.getLogger("MyHttpTrigger_Function")

def main(req: func.HttpRequest) -> func.HttpResponse:
    invocation_id = os.environ.get("InvocationID", None)
    logging_prefix = f"[InvocationId: {invocation_id}]" if invocation_id else "[No InvocationId]"
    logger.info(f"{logging_prefix} MyHttpTrigger_Function processed a request.")

    action_name = None
    params_req = {}
    try:
        if req.method != "POST":
            return func.HttpResponse(
                json.dumps({"error": "MethodNotAllowed", "message": "Solo se permite el método POST."}),
                status_code=405,
                mimetype="application/json"
            )
        try:
            req_body = req.get_json()
        except ValueError:
            logger.error(f"{logging_prefix} Invalid JSON received in request body.")
            return func.HttpResponse(
                json.dumps({"error": "InvalidJSON", "message": "El cuerpo de la solicitud no es un JSON válido."}),
                status_code=400,
                mimetype="application/json"
            )
        action_name = req_body.get('action')
        params_req = req_body.get('params', {})
        if not action_name:
            logger.error(f"{logging_prefix} 'action' missing in request body.")
            return func.HttpResponse(
                json.dumps({"error": "MissingAction", "message": "El campo 'action' es requerido en el cuerpo JSON."}),
                status_code=400,
                mimetype="application/json"
            )
        logger.info(f"{logging_prefix} Request validated. Action: '{action_name}', Params keys: {list(params_req.keys())}")
    except Exception as e:
        logger.exception(f"{logging_prefix} Unexpected error during request validation: {e}")
        return func.HttpResponse(
             json.dumps({"error": "BadRequest", "message": f"Error inesperado al procesar la solicitud: {str(e)}"}),
             status_code=400,
             mimetype="application/json"
        )

    try:
        credential = DefaultAzureCredential()
        # Es buena práctica verificar el token aquí si quieres un fallo rápido en caso de problemas de identidad.
        try:
            token_test = credential.get_token(*constants.GRAPH_API_DEFAULT_SCOPE)
            logger.info(f"{logging_prefix} DefaultAzureCredential obtained successfully. Token for {constants.GRAPH_API_DEFAULT_SCOPE[0]} will expire at {token_test.expires_on}.")
        except CredentialUnavailableError as cred_err:
            logger.error(f"{logging_prefix} Credential unavailable: {cred_err}. Asegúrese de que la Identidad Administrada esté configurada y con permisos, o que haya iniciado sesión localmente (ej. az login).")
            return func.HttpResponse(
                  json.dumps({"error": "AuthenticationError", "message": f"No se pudieron obtener las credenciales de autenticación: {str(cred_err)}"}),
                  status_code=500,
                  mimetype="application/json"
            )
        except Exception as token_err:
             logger.error(f"{logging_prefix} Error obtaining initial token: {token_err}. Verifique los permisos de la Identidad Administrada.")
             return func.HttpResponse(
                  json.dumps({"error": "AuthenticationError", "message": f"Error al obtener el token inicial: {str(token_err)}"}),
                  status_code=500,
                  mimetype="application/json"
             )

        auth_http_client = AuthenticatedHttpClient(credential)
        logger.info(f"{logging_prefix} Authenticated HTTP client initialized.")
    except Exception as e:
        logger.exception(f"{logging_prefix} Error during authentication setup: {e}")
        return func.HttpResponse(
             json.dumps({"error": "SetupError", "message": f"Error interno durante la configuración de autenticación: {str(e)}"}),
             status_code=500,
             mimetype="application/json"
        )

    try:
        action_function = mapping_actions.ACTION_MAP.get(action_name)
        if not action_function:
            logger.error(f"{logging_prefix} Action '{action_name}' not found in ACTION_MAP.")
            return func.HttpResponse(
                json.dumps({"error": "ActionNotFound", "message": f"La acción '{action_name}' no es válida."}),
                status_code=400,
                mimetype="application/json"
            )
        logger.info(f"{logging_prefix} Executing action '{action_name}' with function {action_function.__name__} from module {action_function.__module__}")
        result = action_function(auth_http_client, params_req)

        if isinstance(result, dict) and result.get("error"):
             logger.error(f"{logging_prefix} Action '{action_name}' failed with error: {result}")
             status_code = result.get("http_status", 500)
             if 200 <= status_code < 300:
                  status_code = 500
             return func.HttpResponse(
                 json.dumps(result),
                 status_code=status_code,
                 mimetype="application/json"
             )
        elif isinstance(result, bytes):
            logger.info(f"{logging_prefix} Action '{action_name}' executed successfully, returning binary data.")
            mimetype_bin = "application/octet-stream"
            if "photo" in action_name.lower() or action_name.endswith("_get_my_photo"):
                mimetype_bin = "image/jpeg"
            return func.HttpResponse(
                result,
                status_code=200,
                mimetype=mimetype_bin
            )
        else:
             logger.info(f"{logging_prefix} Action '{action_name}' executed successfully.")
             return func.HttpResponse(
                 json.dumps(result),
                 status_code=200,
                 mimetype="application/json"
             )
    except Exception as e:
        logger.exception(f"{logging_prefix} Unexpected error during action execution for '{action_name}': {e}")
        return func.HttpResponse(
             json.dumps({"error": "ExecutionError", "message": f"Error inesperado al ejecutar la acción '{action_name}': {str(e)}"}),
             status_code=500,
             mimetype="application/json"
        )