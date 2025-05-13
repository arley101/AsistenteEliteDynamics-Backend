import logging
import json
import azure.functions as func
from azure.identity import DefaultAzureCredential, CredentialUnavailableError
import os # Para acceder a InvocationId

# Importamos el ejecutor y las constantes de nuestros módulos
from . import ejecutor # Asumiendo que ejecutor.py está en el mismo directorio
from .shared import constants # Nuestro archivo de constantes
# Asumimos que crearemos un http_client en shared/helpers/http_client.py
from .shared.helpers.http_client import AuthenticatedHttpClient 

# Configuración del logger principal para la función
logger = logging.getLogger("MyHttpTrigger")

def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Punto de entrada principal para la Azure Function HTTP.
    Recibe la solicitud, autentica usando Managed Identity, ejecuta la acción solicitada
    y devuelve la respuesta.
    """
    # Obtenemos el ID de invocación para correlacionar logs
    invocation_id = os.environ.get("InvocationID", None)
    logging_prefix = f"[InvocationId: {invocation_id}]" if invocation_id else "[No InvocationId]"
    logger.info(f"{logging_prefix} Python HTTP trigger function processed a request.")

    # --- 1. Validación de la Solicitud ---
    action_name = None
    params = {}
    try:
        # Asegurarnos de que el método es POST (aunque function.json ya lo restringe)
        if req.method != "POST":
            logger.warning(f"{logging_prefix} Received non-POST request: {req.method}")
            return func.HttpResponse(
                 json.dumps({"error": "MethodNotAllowed", "message": "Solo se permite el método POST."}),
                 status_code=405,
                 mimetype="application/json"
            )
        
        # Intentar obtener el cuerpo JSON
        try:
            req_body = req.get_json()
        except ValueError:
            logger.error(f"{logging_prefix} Invalid JSON received in request body.")
            return func.HttpResponse(
                 json.dumps({"error": "InvalidJSON", "message": "El cuerpo de la solicitud no es un JSON válido."}),
                 status_code=400,
                 mimetype="application/json"
            )

        # Extraer 'action' y 'params'
        action_name = req_body.get('action')
        params = req_body.get('params', {}) # Params es opcional, por defecto es {}

        if not action_name:
            logger.error(f"{logging_prefix} 'action' missing in request body.")
            return func.HttpResponse(
                 json.dumps({"error": "MissingAction", "message": "El campo 'action' es requerido en el cuerpo JSON."}),
                 status_code=400,
                 mimetype="application/json"
            )
        
        logger.info(f"{logging_prefix} Request validated. Action: '{action_name}', Params keys: {list(params.keys())}")

    except Exception as e:
        logger.exception(f"{logging_prefix} Unexpected error during request validation: {e}")
        return func.HttpResponse(
             json.dumps({"error": "BadRequest", "message": "Error inesperado al procesar la solicitud."}),
             status_code=400,
             mimetype="application/json"
        )

    # --- 2. Configuración de Autenticación y Cliente HTTP ---
    try:
        # DefaultAzureCredential intentará varios métodos (Managed Identity, variables de entorno, etc.)
        # En Azure, usará la Identidad Administrada de la Function App.
        # Localmente, puede usar credenciales de Azure CLI, VS Code, etc.
        credential = DefaultAzureCredential()
        
        # Verificar si la credencial está disponible (útil para diagnóstico temprano)
        # Intentamos obtener un token para Graph solo para asegurarnos de que la credencial funciona
        # Podríamos omitir esto si causa latencia, pero es bueno para validar la configuración.
        try:
             token_test = credential.get_token(*constants.GRAPH_API_DEFAULT_SCOPE)
             logger.info(f"{logging_prefix} DefaultAzureCredential obtained successfully.")
             # Opcional: loguear expiración o algún detalle del token si es necesario para debug
             # logger.debug(f"{logging_prefix} Token expires at: {token_test.expires_on}")
        except CredentialUnavailableError as cred_err:
             logger.error(f"{logging_prefix} Credential unavailable: {cred_err}. Asegúrese de que la Identidad Administrada esté configurada o que haya iniciado sesión localmente (ej. az login).")
             return func.HttpResponse(
                  json.dumps({"error": "AuthenticationError", "message": "No se pudieron obtener las credenciales de autenticación."}),
                  status_code=500,
                  mimetype="application/json"
             )
        except Exception as token_err: # Captura otros errores de get_token (permisos, etc.)
             logger.error(f"{logging_prefix} Error obtaining initial token: {token_err}. Verifique los permisos de la Identidad Administrada.")
             return func.HttpResponse(
                  json.dumps({"error": "AuthenticationError", "message": f"Error al obtener el token inicial: {str(token_err)}"}),
                  status_code=500,
                  mimetype="application/json"
             )

        # Crear nuestro cliente HTTP autenticado (lo definiremos en el paso siguiente)
        http_client = AuthenticatedHttpClient(credential)
        logger.info(f"{logging_prefix} Authenticated HTTP client initialized.")

    except Exception as e:
        logger.exception(f"{logging_prefix} Error during authentication setup: {e}")
        return func.HttpResponse(
             json.dumps({"error": "SetupError", "message": "Error interno durante la configuración de autenticación."}),
             status_code=500,
             mimetype="application/json"
        )

    # --- 3. Ejecución de la Acción ---
    try:
        # Llamar al módulo ejecutor para manejar la acción específica
        result = ejecutor.execute_action(action_name, params, http_client, logging_prefix)

        # Asumimos que el ejecutor devuelve un diccionario (resultado o error)
        if isinstance(result, dict) and result.get("error"):
             # Si el ejecutor o la acción devolvió un error conocido, lo pasamos tal cual
             logger.error(f"{logging_prefix} Action '{action_name}' failed with error: {result}")
             status_code = result.get("status_code", 500) # Usar 500 si no se especifica
             # Asegurarse de no retornar códigos 2xx en caso de error
             if 200 <= status_code < 300:
                  status_code = 500
             return func.HttpResponse(
                 json.dumps(result),
                 status_code=status_code,
                 mimetype="application/json"
             )
        else:
             # Éxito
             logger.info(f"{logging_prefix} Action '{action_name}' executed successfully.")
             return func.HttpResponse(
                 json.dumps(result), # Devolver el resultado directamente
                 status_code=200,
                 mimetype="application/json"
             )

    except Exception as e:
        # Capturar cualquier error inesperado durante la ejecución de la acción
        logger.exception(f"{logging_prefix} Unexpected error during action execution for '{action_name}': {e}")
        return func.HttpResponse(
             json.dumps({"error": "ExecutionError", "message": f"Error inesperado al ejecutar la acción '{action_name}'."}),
             status_code=500,
             mimetype="application/json"
        )