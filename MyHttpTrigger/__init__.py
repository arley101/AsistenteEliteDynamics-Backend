# MyHttpTrigger/__init__.py (PRUEBA MINIMALISTA v3 - INSPECCIÓN INTERNA DE MSAL)
import logging
import azure.functions as func
import os
import sys

logging.critical("***** PYTHON __init__.py INICIO DEL ARCHIVO - PRUEBA MINIMALISTA v3 *****")

msal_import_successful = False
msal_specific_error_message = "Error desconocido durante importación de MSAL."
path_check_message_v3 = "Verificación de ruta v3 no realizada."
MsalUiRequiredException = BaseException 
MsalServiceError = BaseException    

try:
    logging.critical("***** PYTHON __init__.py - INTENTANDO IMPORTAR MSAL (v3) *****")
    from msal import ConfidentialClientApplication
    from msal.exceptions import MsalUiRequiredException as MsalExImported_UI, MsalServiceError as MsalExImported_Service
    
    MsalUiRequiredException = MsalExImported_UI
    MsalServiceError = MsalExImported_Service
    msal_import_successful = True
    logging.critical("***** PYTHON __init__.py - IMPORTACIÓN DE MSAL Y EXCEPCIONES EXITOSA (v3) *****")

except ModuleNotFoundError as e_mnfe:
    msal_specific_error_message = f"ModuleNotFoundError: {e_mnfe}"
    logging.critical(f"***** FALLO CRÍTICO AL IMPORTAR MSAL (ModuleNotFoundError, v3): {msal_specific_error_message} *****", exc_info=True)

except Exception as e_other_msal:
    msal_specific_error_message = f"Excepción General al importar MSAL (v3): {e_other_msal}"
    logging.critical(f"***** FALLO CRÍTICO AL IMPORTAR MSAL (Otra Excepción, v3): {msal_specific_error_message} *****", exc_info=True)

logging.critical(f"***** PYTHON __init__.py - ESTADO DE IMPORTACIÓN MSAL (v3): {msal_import_successful}, Error: {msal_specific_error_message} *****")

logger_main = logging.getLogger("MinimalTestLoggerV3.main")

def main(req: func.HttpRequest) -> func.HttpResponse:
    logger_main.critical("***** PYTHON main() - FUNCIÓN INVOCADA (PRUEBA MINIMALISTA v3) *****")
    request_id = req.headers.get("X-Request-ID", "N/A") 
    logger_main.critical(f"RequestId: {request_id} - Dentro de main (v3).")

    if not msal_import_successful:
        # --- Inicio Bloque de Diagnóstico Detallado v3 ---
        expected_site_packages_path = "/home/site/wwwroot/.python_packages/lib/python3.11/site-packages"
        expected_msal_package_path = os.path.join(expected_site_packages_path, "msal")
        expected_msal_init_path = os.path.join(expected_msal_package_path, "__init__.py")

        msal_package_path_exists = os.path.exists(expected_msal_package_path)
        msal_init_file_exists = os.path.exists(expected_msal_init_path)
        
        msal_package_content_message = f"Contenido de '{expected_msal_package_path}' no verificado."
        if msal_package_path_exists:
            try:
                content = os.listdir(expected_msal_package_path)
                msal_package_content_message = f"Contenido de '{expected_msal_package_path}' (primeros 10): {content[:10]}"
            except Exception as e_listdir_msal:
                msal_package_content_message = f"Error listando '{expected_msal_package_path}': {e_listdir_msal}"
        else:
            msal_package_content_message = f"'{expected_msal_package_path}' NO encontrado, no se pudo listar contenido."

        site_packages_content_message = "Contenido de site-packages no verificado."
        if os.path.exists(expected_site_packages_path):
            try:
                content = os.listdir(expected_site_packages_path)
                site_packages_content_message = f"Contenido de '{expected_site_packages_path}' (primeros 10, para contexto): {content[:10]}"
            except Exception as e_listdir_sp:
                site_packages_content_message = f"Error listando '{expected_site_packages_path}': {e_listdir_sp}"
        else:
            site_packages_content_message = f"'{expected_site_packages_path}' NO encontrado."

        path_check_message_v3 = (
            f"Diagnóstico v3: "
            f"Ruta msal ('{expected_msal_package_path}') ¿Existe?: {msal_package_path_exists}. "
            f"Ruta msal/__init__.py ('{expected_msal_init_path}') ¿Existe?: {msal_init_file_exists}. "
            f"{msal_package_content_message}. "
            f"{site_packages_content_message}."
        )
        # --- Fin Bloque de Diagnóstico Detallado v3 ---
        
        logger_main.critical(f"RequestId: {request_id} - MSAL NO FUE IMPORTADO (v3). {path_check_message_v3}")
        
        return func.HttpResponse(
             f"ERROR: MSAL no pudo ser importado. Detalles: {msal_specific_error_message}. {path_check_message_v3}",
             status_code=500
        )
    
    # ... (resto de la función main como en v2, para el caso de éxito) ...
    logger_main.critical(f"RequestId: {request_id} - MSAL PARECE IMPORTADO (v3). Intentando usar ConfidentialClientApplication.")
    try:
        client_id = os.environ.get("CLIENT_ID", "dummy_client_id_for_test")
        tenant_id = os.environ.get("TENANT_ID", "dummy_tenant_id_for_test")
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        app = ConfidentialClientApplication(client_id, authority=authority)
        logger_main.critical(f"RequestId: {request_id} - Instancia de ConfidentialClientApplication creada (v3) con CLIENT_ID: {client_id}")
        return func.HttpResponse(
            f"PRUEBA MINIMALISTA v3: MSAL importado y ConfidentialClientApplication instanciado. CLIENT_ID usado: {client_id}.",
            status_code=200
        )
    except Exception as e_cca:
        logger_main.critical(f"RequestId: {request_id} - ERROR AL INSTANCIAR o USAR CCA (v3): {e_cca}", exc_info=True)
        return func.HttpResponse(
             f"ERROR: MSAL importado pero falló al usar CCA (v3). Detalles: {e_cca}",
             status_code=500
        )