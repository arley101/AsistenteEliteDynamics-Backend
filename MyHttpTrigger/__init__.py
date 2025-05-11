# MyHttpTrigger/__init__.py (PRUEBA DE DIAGNÓSTICO MINIMALISTA)
import logging
import azure.functions as func
import os
import sys

# PRIMERA LÍNEA EJECUTABLE DE PYTHON - PRUEBA DE LOGGING
logging.critical("***** PYTHON __init__.py INICIO DEL ARCHIVO - PRUEBA DE LOGGING 1 *****")

msal_import_successful = False
msal_specific_error_message = "Error desconocido durante importación de MSAL."
MsalUiRequiredException = BaseException # Dummies por si la importación falla
MsalServiceError = BaseException    # Dummies por si la importación falla

try:
    logging.critical("***** PYTHON __init__.py - INTENTANDO IMPORTAR MSAL *****")
    from msal import ConfidentialClientApplication
    from msal.exceptions import MsalUiRequiredException as MsalExImported_UI, MsalServiceError as MsalExImported_Service
    
    # Si llegamos aquí, la importación fue exitosa, reasignamos las excepciones reales
    MsalUiRequiredException = MsalExImported_UI
    MsalServiceError = MsalExImported_Service
    msal_import_successful = True
    logging.critical("***** PYTHON __init__.py - IMPORTACIÓN DE MSAL Y EXCEPCIONES EXITOSA *****")

except ModuleNotFoundError as e_mnfe:
    msal_specific_error_message = f"ModuleNotFoundError: {e_mnfe}"
    logging.critical(f"***** FALLO CRÍTICO AL IMPORTAR MSAL (ModuleNotFoundError): {msal_specific_error_message} *****", exc_info=True)
    # MsalUiRequiredException y MsalServiceError ya están como BaseException

except Exception as e_other_msal:
    msal_specific_error_message = f"Excepción General al importar MSAL: {e_other_msal}"
    logging.critical(f"***** FALLO CRÍTICO AL IMPORTAR MSAL (Otra Excepción): {msal_specific_error_message} *****", exc_info=True)
    # MsalUiRequiredException y MsalServiceError ya están como BaseException

logging.critical(f"***** PYTHON __init__.py - ESTADO DE IMPORTACIÓN MSAL: {msal_import_successful}, Error: {msal_specific_error_message} *****")

# Logger simple para la función main
logger_main = logging.getLogger("MinimalTestLogger.main")

def main(req: func.HttpRequest) -> func.HttpResponse:
    logger_main.critical("***** PYTHON main() - FUNCIÓN INVOCADA (PRUEBA MINIMALISTA) *****")
    request_id = req.headers.get("X-Request-ID", "N/A") # Simple ID
    logger_main.critical(f"RequestId: {request_id} - Dentro de main.")

    if not msal_import_successful:
        logger_main.critical(f"RequestId: {request_id} - MSAL NO FUE IMPORTADO CORRECTAMENTE. Error: {msal_specific_error_message}")
        # ESTA ES LA RESPUESTA HTTP QUE ESPERAMOS VER EN CURL/POSTMAN SI MSAL FALLA
        return func.HttpResponse(
             f"ERROR: MSAL no pudo ser importado. Detalles: {msal_specific_error_message}",
             status_code=500
        )
    
    logger_main.critical(f"RequestId: {request_id} - MSAL PARECE IMPORTADO. Intentando usar ConfidentialClientApplication.")
    
    try:
        client_id = os.environ.get("CLIENT_ID", "dummy_client_id_for_test") # Usar get para evitar KeyError si no está
        tenant_id = os.environ.get("TENANT_ID", "dummy_tenant_id_for_test") # Usar get para evitar KeyError si no está
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        
        app = ConfidentialClientApplication(client_id, authority=authority)
        logger_main.critical(f"RequestId: {request_id} - Instancia de ConfidentialClientApplication creada exitosamente con CLIENT_ID: {client_id}")
        
        return func.HttpResponse(
            f"PRUEBA MINIMALISTA: MSAL importado y ConfidentialClientApplication instanciado. CLIENT_ID usado: {client_id}.",
            status_code=200
        )

    except Exception as e_cca:
        logger_main.critical(f"RequestId: {request_id} - ERROR AL INSTANCIAR o USAR ConfidentialClientApplication: {e_cca}", exc_info=True)
        # ESTA ES OTRA RESPUESTA HTTP DE ERROR SI MSAL SE IMPORTÓ PERO FALLA AL USARSE
        return func.HttpResponse(
             f"ERROR: MSAL importado pero falló al usar ConfidentialClientApplication. Detalles: {e_cca}",
             status_code=500
        )