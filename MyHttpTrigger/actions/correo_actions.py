# MyHttpTrigger/actions/correo_actions.py
import logging
import requests # Solo para tipos de excepción
import json
from typing import Dict, List, Optional, Union, Any

# Importar helper y constantes desde la estructura compartida
try:
    from ..shared.helpers.http_client import hacer_llamada_api
    from ..shared.constants import BASE_URL, GRAPH_API_DEFAULT_TIMEOUT, APP_NAME
except ImportError as e:
    # Este error es crítico para el funcionamiento del módulo.
    logging.critical(f"Error CRÍTICO importando dependencias compartidas en Correo: {e}. "
                     "Verifica la estructura del proyecto y PYTHONPATH.", exc_info=True)
    # Definir fallbacks o simplemente permitir que el módulo no cargue correctamente
    # lo cual será capturado por mapping_actions.py
    BASE_URL = "https://graph.microsoft.com/v1.0" # Fallback
    GRAPH_API_DEFAULT_TIMEOUT = 45 # Fallback
    APP_NAME = "EliteDynamicsPro" # Fallback
    # No es ideal definir un mock de hacer_llamada_api aquí si la real no se puede importar,
    # ya que las funciones fallarán de todos modos. Dejar que falle la importación es más limpio.
    raise ImportError(f"No se pudo importar 'hacer_llamada_api' o constantes: {e}") from e

logger = logging.getLogger(f"{APP_NAME}.actions.correo")

# ---- Helper Interno para Normalizar Destinatarios ----
def _normalize_recipients(
    rec_input: Optional[Union[str, List[str], List[Dict[str, Any]]]],
    type_name: str = "destinatario"
) -> List[Dict[str, Any]]:
    """
    Normaliza diferentes formatos de entrada de destinatarios a la estructura de Graph API
    esperada: [{"emailAddress": {"address": "email@example.com"}}, ...].
    Un string puede contener múltiples emails separados por ; o ,.
    """
    recipients_list: List[Dict[str, Any]] = []
    if not rec_input:
        return recipients_list

    input_list_processed: List[Any] = []
    if isinstance(rec_input, str):
        # Dividir por coma y/o punto y coma, luego limpiar espacios
        emails_from_string = [email.strip() for email in rec_input.replace(';', ',').split(',') if email.strip()]
        input_list_processed.extend(emails_from_string)
    elif isinstance(rec_input, list):
        input_list_processed = rec_input
    else:
        logger.error(f"Formato inválido para {type_name}: Se esperaba str o List. Se recibió {type(rec_input)}.")
        # Podríamos lanzar un TypeError aquí, o devolver lista vacía para que falle la validación posterior si es crítico.
        # Por ahora, devolvemos lista vacía y la función que llama debe validar si hay destinatarios.
        return []

    for item in input_list_processed:
        if isinstance(item, str) and item.strip() and "@" in item: # Validación muy básica de email
            recipients_list.append({"emailAddress": {"address": item.strip()}})
        elif isinstance(item, dict) and \
             isinstance(item.get("emailAddress"), dict) and \
             isinstance(item["emailAddress"].get("address"), str) and \
             item["emailAddress"]["address"].strip() and "@" in item["emailAddress"]["address"]:
            # Ya está en el formato correcto o es un objeto de contacto/usuario válido
            recipients_list.append(item)
        else:
            logger.warning(f"Item inválido o malformado en lista de {type_name}: '{item}'. Se ignorará.")
            
    if not recipients_list:
        logger.warning(f"La entrada para '{type_name}' ('{rec_input}') no produjo destinatarios válidos.")

    return recipients_list

# ---- FUNCIONES DE ACCIÓN PARA CORREO ----

def listar_correos(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Lista correos de una carpeta específica, manejando paginación completa hasta max_items.
    """
    mailbox: str = parametros.get('mailbox', 'me')
    folder_id: str = parametros.get('folder_id', 'Inbox')
    top_per_page: int = min(int(parametros.get('top_per_page', 25)), 50) # Graph recomienda max 50 para mensajes
    max_items_total: int = int(parametros.get('max_items_total', 100))
    select: Optional[str] = parametros.get('select')
    filter_query: Optional[str] = parametros.get('filter_query')
    order_by: Optional[str] = parametros.get('order_by', 'receivedDateTime desc')

    url_base = f"{BASE_URL}/users/{mailbox}/mailFolders/{folder_id}/messages"
    
    query_params: Dict[str, Any] = {'$top': top_per_page}
    if select: query_params['$select'] = select
    if filter_query: query_params['$filter'] = filter_query
    if order_by: query_params['$orderby'] = order_by

    all_messages: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0
    
    logger.info(f"Listando correos para '{mailbox}', carpeta '{folder_id}' (max_total: {max_items_total}, por_pagina: {top_per_page})")

    try:
        while current_url and len(all_messages) < max_items_total:
            page_count += 1
            params_for_call = query_params if current_url == url_base and page_count == 1 else None
            
            logger.debug(f" Obteniendo página {page_count} de correos desde: {current_url} (params si es 1a pág: {params_for_call})")
            response_data = hacer_llamada_api("GET", current_url, headers, params=params_for_call, timeout=GRAPH_API_DEFAULT_TIMEOUT)

            if response_data and isinstance(response_data, dict) and 'value' in response_data:
                messages_in_page = response_data.get('value', [])
                if not isinstance(messages_in_page, list):
                    logger.warning("Respuesta de 'value' no es una lista. Terminando paginación.")
                    break
                
                for msg in messages_in_page:
                    if len(all_messages) < max_items_total:
                        all_messages.append(msg)
                    else:
                        break # Límite total alcanzado
                
                current_url = response_data.get('@odata.nextLink')
                if not current_url or len(all_messages) >= max_items_total:
                    logger.debug("No hay '@odata.nextLink' o se alcanzó max_items_total. Fin de paginación.")
                    break
            else:
                logger.warning(f"Respuesta inesperada o vacía de Graph API al listar correos (página {page_count}).")
                break
        
        logger.info(f"Total correos recuperados: {len(all_messages)} tras {page_count} página(s).")
        return {"status": "success", "data": all_messages, "total_retrieved": len(all_messages), "pages_processed": page_count}
    except Exception as e:
        logger.error(f"Error listando correos: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al listar correos: {type(e).__name__}", "details": str(e)}


def leer_correo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    mailbox: str = parametros.get('mailbox', 'me')
    message_id: Optional[str] = parametros.get('message_id')
    select: Optional[str] = parametros.get('select')
    expand: Optional[str] = parametros.get('expand') # ej. "attachments"

    if not message_id: 
        return {"status": "error", "message": "Parámetro 'message_id' es requerido."}

    url = f"{BASE_URL}/users/{mailbox}/messages/{message_id}"
    params_query: Dict[str, Any] = {}
    if select: params_query['$select'] = select
    if expand: params_query['$expand'] = expand
    
    logger.info(f"Leyendo correo '{message_id}' para '{mailbox}' (Select: {select or 'default'}, Expand: {expand or 'none'})")
    try:
        email_data = hacer_llamada_api("GET", url, headers, params=params_query or None, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        if email_data and isinstance(email_data, dict): # Verificar que sea dict
            return {"status": "success", "data": email_data}
        else:
            logger.warning(f"No se pudo obtener el correo '{message_id}' o la respuesta no fue un JSON válido.")
            return {"status": "error", "message": f"No se pudo obtener el correo '{message_id}' o la respuesta fue inesperada."}
    except Exception as e:
        logger.error(f"Error leyendo correo '{message_id}': {type(e).__name__} - {e}", exc_info=True)
        # Si el error es un 404 de requests.exceptions.HTTPError, podríamos dar un mensaje más específico
        if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 404:
            return {"status": "error", "message": f"Correo con ID '{message_id}' no encontrado.", "details": str(e)}
        return {"status": "error", "message": f"Error al leer correo: {type(e).__name__}", "details": str(e)}


def enviar_correo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    mailbox: str = parametros.get('mailbox', 'me')
    destinatario_in = parametros.get('destinatario')
    asunto: Optional[str] = parametros.get('asunto')
    mensaje: Optional[str] = parametros.get('mensaje')
    tipo_cuerpo: str = parametros.get('tipo_cuerpo', 'HTML').upper()
    cc_in = parametros.get('cc')
    bcc_in = parametros.get('bcc')
    # attachments: Espera una lista de diccionarios con el formato de Graph API.
    # Ejemplo: [{"@odata.type": "#microsoft.graph.fileAttachment", "name": "archivo.txt", "contentBytes": "BASE64_CONTENT"}]
    attachments: Optional[List[dict]] = parametros.get('attachments')
    save_to_sent: bool = str(parametros.get('save_to_sent', "true")).lower() == "true"

    if destinatario_in is None or asunto is None or mensaje is None: # Asunto y mensaje pueden ser vacíos, pero no None
        return {"status": "error", "message": "Parámetros 'destinatario', 'asunto' y 'mensaje' son requeridos."}
    if tipo_cuerpo not in ["HTML", "TEXT"]:
        return {"status": "error", "message": "Parámetro 'tipo_cuerpo' debe ser 'HTML' o 'Text'."}

    try:
        to_recipients = _normalize_recipients(destinatario_in, "destinatario")
        if not to_recipients: return {"status": "error", "message": "Al menos un destinatario válido es requerido en 'destinatario'."}
        cc_recipients = _normalize_recipients(cc_in, "cc")
        bcc_recipients = _normalize_recipients(bcc_in, "bcc")
    except TypeError as e:
        return {"status": "error", "message": f"Error en formato de destinatarios: {e}"}

    message_payload: Dict[str, Any] = {
        "subject": asunto,
        "body": {"contentType": tipo_cuerpo, "content": mensaje},
        "toRecipients": to_recipients
    }
    if cc_recipients: message_payload["ccRecipients"] = cc_recipients
    if bcc_recipients: message_payload["bccRecipients"] = bcc_recipients
    if attachments and isinstance(attachments, list): message_payload["attachments"] = attachments

    final_payload = {"message": message_payload, "saveToSentItems": save_to_sent } # API espera bool aquí
    url = f"{BASE_URL}/users/{mailbox}/sendMail"
    logger.info(f"Intentando enviar correo para '{mailbox}'. Asunto: '{asunto}'")
    try:
        # sendMail devuelve 202 Accepted (sin cuerpo).
        hacer_llamada_api("POST", url, headers, json_data=final_payload, timeout=GRAPH_API_DEFAULT_TIMEOUT, expect_json=False)
        return {"status": "success", "message": "Solicitud de envío de correo aceptada por el servidor."}
    except Exception as e:
        logger.error(f"Error enviando correo: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al enviar correo: {type(e).__name__}", "details": str(e)}

def guardar_borrador(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    mailbox: str = parametros.get('mailbox', 'me')
    asunto: Optional[str] = parametros.get('asunto', "") # Asunto puede ser vacío
    mensaje: Optional[str] = parametros.get('mensaje', "") # Cuerpo puede ser vacío
    tipo_cuerpo: str = parametros.get('tipo_cuerpo', 'HTML').upper()
    destinatario_in = parametros.get('destinatario')
    cc_in = parametros.get('cc')
    bcc_in = parametros.get('bcc')
    attachments: Optional[List[dict]] = parametros.get('attachments')

    # Asunto y mensaje pueden ser strings vacíos, pero no None si se quiere un borrador con esos campos
    # Aquí no los validamos como requeridos, Graph permite borradores muy mínimos.

    try:
        to_recipients = _normalize_recipients(destinatario_in, "destinatario")
        cc_recipients = _normalize_recipients(cc_in, "cc")
        bcc_recipients = _normalize_recipients(bcc_in, "bcc")
    except TypeError as e:
        return {"status": "error", "message": f"Error en formato de destinatarios: {e}"}

    message_payload: Dict[str, Any] = {
        "subject": asunto,
        "body": {"contentType": tipo_cuerpo, "content": mensaje}
    }
    if to_recipients: message_payload["toRecipients"] = to_recipients
    if cc_recipients: message_payload["ccRecipients"] = cc_recipients
    if bcc_recipients: message_payload["bccRecipients"] = bcc_recipients
    if attachments: message_payload["attachments"] = attachments

    url = f"{BASE_URL}/users/{mailbox}/messages"
    logger.info(f"Guardando borrador para '{mailbox}'. Asunto: '{asunto if asunto else '(Sin asunto)'}'")
    try:
        draft_message = hacer_llamada_api("POST", url, headers, json_data=message_payload, timeout=GRAPH_API_DEFAULT_TIMEOUT)
        if draft_message and isinstance(draft_message, dict):
            return {"status": "success", "data": draft_message, "message": "Borrador guardado exitosamente."}
        else: # Esto podría ocurrir si la API devuelve 201 pero sin cuerpo, o error del helper
            return {"status": "error", "message": "No se pudo guardar el borrador o la respuesta fue inesperada."}
    except Exception as e:
        logger.error(f"Error guardando borrador: {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al guardar borrador: {type(e).__name__}", "details": str(e)}

def enviar_borrador(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    mailbox: str = parametros.get('mailbox', 'me')
    message_id: Optional[str] = parametros.get('message_id')
    if not message_id: return {"status": "error", "message": "Parámetro 'message_id' del borrador es requerido."}

    url = f"{BASE_URL}/users/{mailbox}/messages/{message_id}/send"
    logger.info(f"Enviando borrador '{message_id}' para '{mailbox}'")
    try:
        hacer_llamada_api("POST", url, headers, timeout=GRAPH_API_DEFAULT_TIMEOUT, expect_json=False)
        return {"status": "success", "message": "Solicitud de envío de borrador aceptada."}
    except Exception as e:
        logger.error(f"Error enviando borrador '{message_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al enviar borrador: {type(e).__name__}", "details": str(e)}

def responder_correo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    mailbox: str = parametros.get('mailbox', 'me')
    message_id: Optional[str] = parametros.get('message_id')
    mensaje_respuesta: Optional[str] = parametros.get('mensaje_respuesta')
    reply_all: bool = str(parametros.get('reply_all', "false")).lower() == "true"
    to_recipients_override_in = parametros.get('to_recipients_override')
    # attachments_respuesta: Lista de dicts con formato Graph API para adjuntos en la respuesta
    attachments_respuesta: Optional[List[dict]] = parametros.get('attachments_respuesta')


    if not message_id or mensaje_respuesta is None:
        return {"status": "error", "message": "Parámetros 'message_id' y 'mensaje_respuesta' son requeridos."}

    action = "replyAll" if reply_all else "reply"
    url = f"{BASE_URL}/users/{mailbox}/messages/{message_id}/{action}"
    
    # El payload para reply/replyAll debe estar dentro de un objeto "message" si quieres modificar
    # el cuerpo o los destinatarios de la respuesta. Solo 'comment' va en el nivel raíz.
    payload: Dict[str, Any] = {"comment": mensaje_respuesta} # Comentario se añade al cuerpo de la respuesta
    message_details_for_reply: Dict[str, Any] = {}

    if to_recipients_override_in:
        try:
            norm_to = _normalize_recipients(to_recipients_override_in, "to_recipients_override (respuesta)")
            if norm_to: message_details_for_reply["toRecipients"] = norm_to
        except TypeError as e: return {"status": "error", "message": f"Error en 'to_recipients_override': {e}"}
    
    if attachments_respuesta and isinstance(attachments_respuesta, list):
        message_details_for_reply["attachments"] = attachments_respuesta
    
    if message_details_for_reply: # Si hay detalles para el objeto 'message'
        payload["message"] = message_details_for_reply
    
    logger.info(f"{'Respondiendo a todos' if reply_all else 'Respondiendo'} al correo '{message_id}' para '{mailbox}'")
    try:
        hacer_llamada_api("POST", url, headers, json_data=payload, timeout=GRAPH_API_DEFAULT_TIMEOUT, expect_json=False)
        return {"status": "success", "message": "Solicitud de respuesta enviada."}
    except Exception as e:
        logger.error(f"Error respondiendo al correo '{message_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al responder correo: {type(e).__name__}", "details": str(e)}

def reenviar_correo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    mailbox: str = parametros.get('mailbox', 'me')
    message_id: Optional[str] = parametros.get('message_id')
    destinatarios_in = parametros.get('destinatarios')
    mensaje_reenvio: str = parametros.get('mensaje_reenvio', "") # Comentario opcional
    # attachments_reenvio: Lista de dicts con formato Graph API para adjuntos en el reenvío
    attachments_reenvio: Optional[List[dict]] = parametros.get('attachments_reenvio')


    if not message_id or not destinatarios_in:
        return {"status": "error", "message": "Parámetros 'message_id' y 'destinatarios' son requeridos."}

    try:
        to_recipients = _normalize_recipients(destinatarios_in, "destinatarios (reenvío)")
        if not to_recipients: return {"status": "error", "message": "Al menos un destinatario válido es requerido."}
    except TypeError as e:
        return {"status": "error", "message": f"Error en formato de destinatarios: {e}"}

    url = f"{BASE_URL}/users/{mailbox}/messages/{message_id}/forward"
    payload: Dict[str, Any] = {"toRecipients": to_recipients, "comment": mensaje_reenvio}
    
    # Si se quiere modificar el cuerpo completo del mensaje reenviado (además del comentario)
    # se puede añadir un objeto "message" al payload.
    # Por ahora, solo se usa 'comment'.
    if attachments_reenvio and isinstance(attachments_reenvio, list):
        payload.setdefault("message", {})["attachments"] = attachments_reenvio
    
    logger.info(f"Reenviando correo '{message_id}' para '{mailbox}'")
    try:
        hacer_llamada_api("POST", url, headers, json_data=payload, timeout=GRAPH_API_DEFAULT_TIMEOUT, expect_json=False)
        return {"status": "success", "message": "Solicitud de reenvío de correo aceptada."}
    except Exception as e:
        logger.error(f"Error reenviando correo '{message_id}': {type(e).__name__} - {e}", exc_info=True)
        return {"status": "error", "message": f"Error al reenviar correo: {type(e).__name__}", "details": str(e)}

def eliminar_correo(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    mailbox: str = parametros.get('mailbox', 'me')
    message_id: Optional[str] = parametros.get('message_id')
    if not message_id: return {"status": "error", "message": "Parámetro 'message_id' es requerido."}

    url = f"{BASE_URL}/users/{mailbox}/messages/{message_id}"
    logger.info(f"Eliminando correo '{message_id}' para '{mailbox}' (moviendo a Elementos Eliminados)")
    try:
        hacer_llamada_api("DELETE", url, headers, timeout=GRAPH_API_DEFAULT_TIMEOUT, expect_json=False)
        return {"status": "success", "message": "Correo movido a elementos eliminados."}
    except Exception as e:
        logger.error(f"Error eliminando correo '{message_id}': {type(e).__name__} - {e}", exc_info=True)
        if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 404:
             return {"status": "error", "message": f"Correo con ID '{message_id}' no encontrado para eliminar.", "details": str(e)}
        return {"status": "error", "message": f"Error al eliminar correo: {type(e).__name__}", "details": str(e)}

# --- FIN DEL MÓDULO actions/correo_actions.py ---