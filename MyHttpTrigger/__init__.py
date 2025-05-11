# MyHttpTrigger/__init__.py (PRUEBA MINIMALISTA v2 - VERIFICACIÓN DE RUTA)
import logging
import azure.functions as func
import os
import sys

# PRIMERA LÍNEA EJECUTABLE DE PYTHON - PRUEBA DE LOGGING
logging.critical("***** PYTHON __init__.py INICIO DEL ARCHIVO - PRUEBA MINIMALISTA v2 *****")

msal_import_successful = False
msal_specific_error_message = "Error desconocido durante importación de MSAL."
path_check_message = "Verificación de ruta no realizada."
MsalUiRequiredException = BaseException 
MsalServiceError = BaseException    

try:
    logging.critical("***** PYTHON __init__.py - INTENTANDO IMPORTAR MSAL (v2) *****")
    from msal import ConfidentialClientApplication
    from msal.exceptions import MsalUiRequiredException as MsalExImported_UI, MsalServiceError as MsalExImported_Service
    
    MsalUiRequiredException = MsalExImported_UI
    MsalServiceError = MsalExImported_Service
    msal_import_successful = True
    logging.critical("***** PYTHON __init__.py - IMPORTACIÓN DE MSAL Y EXCEPCIONES EXITOSA (v2) *****")

except ModuleNotFoundError as e_mnfe:
    msal_specific_error_message = f"ModuleNotFoundError: {e_mnfe}"
    logging.critical(f"***** FALLO CRÍTICO AL IMPORTAR MSAL (ModuleNotFoundError, v2): {msal_specific_error_message} *****", exc_info=True)

except Exception as e_other_msal:
    msal_specific_error_message = f"Excepción General al importar MSAL (v2): {e_other_msal}"
    logging.critical(f"***** FALLO CRÍTICO AL IMPORTAR MSAL (Otra Excepción, v2): {msal_specific_error_message} *****", exc_info=True)

logging.critical(f"***** PYTHON __init__.py - ESTADO DE IMPORTACIÓN MSAL (v2): {msal_import_successful}, Error: {msal_specific_error_message} *****")

# Logger simple para la función main
logger_main = logging.getLogger("MinimalTestLoggerV2.main")

def main(req: func.HttpRequest) -> func.HttpResponse:
    logger_main.critical("***** PYTHON main() - FUNCIÓN INVOCADA (PRUEBA MINIMALISTA v2) *****")
    request_id = req.headers.get("X-Request-ID", "N/A") 
    logger_main.critical(f"RequestId: {request_id} - Dentro de main (v2).")

    # VERIFICACIÓN DE RUTA DE MSAL (SOLO SI LA IMPORTACIÓN FALLÓ)
    if not msal_import_successful:
        expected_msal_path = "/home/site/wwwroot/.python_packages/lib/python3.11/site-packages/msal"
        msal_path_exists = os.path.exists(expected_msal_path)
        
        site_packages_path = "/home/site/wwwroot/.python_packages/lib/python3.11/site-packages"
        site_packages_content_message = "Contenido de site-packages no verificado."
        if os.path.exists(site_packages_path):
            try:
                content = os.listdir(site_packages_path)
                site_packages_content_message = f"Contenido de {site_packages_path} (primeros 10): {content[:10]}"
            except Exception as e_listdir:
                site_packages_content_message = f"Error listando {site_packages_path}: {e_listdir}"
        else:
            site_packages_content_message = f"{site_packages_path} NO encontrado."

        path_check_message = f"Se verificó la ruta esperada para msal: '{expected_msal_path}'. ¿Existe?: {msal_path_exists}. {site_packages_content_message}"
        logger_main.critical(f"RequestId: {request_id} - MSAL NO FUE IMPORTADO. {path_check_message}")
        
        # ESTA ES LA RESPUESTA HTTP QUE ESPERAMOS VER EN CURL/POSTMAN CON LA INFO DE RUTA
        return func.HttpResponse(
             f"ERROR: MSAL no pudo ser importado. Detalles: {msal_specific_error_message}. {path_check_message}",
             status_code=500
        )
    
    logger_main.critical(f"RequestId: {request_id} - MSAL PARECE IMPORTADO (v2). Intentando usar ConfidentialClientApplication.")
    
    try:
        client_id = os.environ.get("CLIENT_ID", "dummy_client_id_for_test")
        tenant_id = os.environ.get("TENANT_ID", "dummy_tenant_id_for_test")
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        
        app = ConfidentialClientApplication(client_id, authority=authority)
        logger_main.critical(f"RequestId: {request_id} - Instancia de ConfidentialClientApplication creada (v2) con CLIENT_ID: {client_id}")
        
        return func.HttpResponse(
            f"PRUEBA MINIMALISTA v2: MSAL importado y ConfidentialClientApplication instanciado. CLIENT_ID usado: {client_id}.",
            status_code=200
        )

    except Exception as e_cca:
        logger_main.critical(f"RequestId: {request_id} - ERROR AL INSTANCIAR o USAR CCA (v2): {e_cca}", exc_info=True)
        return func.HttpResponse(
             f"ERROR: MSAL importado pero falló al usar CCA (v2). Detalles: {e_cca}",
             status_code=500
        )