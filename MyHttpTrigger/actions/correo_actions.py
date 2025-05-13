# MyHttpTrigger/actions/correo_actions.py
import logging
import requests # Solo para tipos de excepción y la clase HTTPError
import json
from typing import Dict, List, Optional, Union, Any

# Importar el cliente autenticado y las constantes
from ..shared.helpers.http_client import AuthenticatedHttpClient
from ..shared import constants

logger = logging.getLogger(__name__)

# --- Constantes de Scopes (a definir en constants.py idealmente) ---
# Si no están en constants.py, usamos el GRAPH_SCOPE general y añadimos un comentario.
# Para que esto funcione como está, asegúrate de que estas constantes existen en tu archivo constants.py:
# constants.GRAPH_SCOPE_MAIL_READ
# constants.GRAPH_SCOPE_MAIL_SEND
# constants.GRAPH_SCOPE_MAIL_READ_WRITE
# Si no, se reemplazarán por constants.GRAPH_SCOPE en el código.

GRAPH_SCOPE_MAIL_READ = getattr(constants, 'GRAPH_SCOPE_MAIL_READ', constants.GRAPH_SCOPE)
GRAPH_SCOPE_MAIL_SEND = getattr(constants, 'GRAPH_SCOPE_MAIL_SEND', constants.GRAPH_SCOPE)
GRAPH_SCOPE_MAIL_READ_WRITE = getattr(constants, 'GRAPH_SCOPE_MAIL_READ_WRITE', constants.GRAPH_SCOPE)

if constants.GRAPH_SCOPE == GRAPH_SCOPE_MAIL_READ:
    logger.warning("Usando GRAPH_SCOPE general para Mail.Read. Considerar definir GRAPH_SCOPE_MAIL_READ en constants.py para permisos más específicos.")
if constants.GRAPH_SCOPE == GRAPH_SCOPE_MAIL_SEND:
    logger.warning("Usando GRAPH_SCOPE general para Mail.Send. Considerar definir GRAPH_SCOPE_MAIL_SEND en constants.py.")
if constants.GRAPH_SCOPE == GRAPH_SCOPE_MAIL_READ_WRITE:
    logger.warning("Usando GRAPH_SCOPE general para Mail.ReadWrite. Considerar definir GRAPH_SCOPE_MAIL_READ_WRITE en constants.py.")


# --- Helper para manejar errores de Correo API de forma centralizada ---
def _handle_email_api_error(e: Exception, action_name: str, params_for_log: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    log_message = f"Error en Email action '{action_name}'"
    safe_params = {}
    if params_for_log:
        # Evitar loguear contenido sensible
        sensitive_keys = ['mensaje', 'mensaje_respuesta', 'mensaje_reenvio', 'attachments', 
                          'attachments_respuesta', 'message_payload', 'final_payload', 
                          'mensaje_contenido', 'destinatario_in', 'cc_in', 'bcc_in', 
                          'destinatarios_in', 'mensaje_comentario']
        safe_params = {k: (v if k not in sensitive_keys else "[CONTENIDO OMITIDO]") for k, v in params_for_log.items()}
        log_message += f" con params: {safe_params}"
    
    logger.error(f"{log_message}: {type(e).__name__} - {str(e)}", exc_info=True) # exc_info=True para traceback completo
    
    details = str(e)
    status_code = 500
    graph_error_code = None # Para códigos de error específicos de Graph

    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
        status_code = e.response.status_code
        try:
            error_data = e.response.json()
            # Graph errors a menudo tienen esta estructura: error > code, message
            error_info = error_data.get("error", {})
            details = error_info.get("message", e.response.text)
            graph_error_code = error_info.get("code")
        except json.JSONDecodeError:
            details = e.response.text # Si la respuesta de error no es JSON
            
    return {
        "status": "error",
        "action": action_name,
        "message": f"Error en {action_name}: {type(e).__name__}", # Mensaje más genérico para el usuario
        "http_status": status_code,
        "details": details, # Detalles técnicos
        "graph_error_code": graph_error_code
    }

# --- Helper común para paginación (adaptado para Correo) ---
def _email_paged_request(
    client: AuthenticatedHttpClient,
    url_base: str,
    scope: str,
    params_input: Dict[str, Any], # Parámetros originales de la función de acción para logging
    query_api_params_initial: Dict[str, Any],
    max_items_total: int,
    action_name_for_log: str
) -> Dict[str, Any]:
    all_items: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0
    # Límite de seguridad para evitar bucles infinitos si algo va mal con @odata.nextLink
    # o si max_items_total es extremadamente grande.
    max_pages_to_fetch = constants.MAX_PAGING_PAGES 

    top_value = query_api_params_initial.get('$top', constants.DEFAULT_PAGING_SIZE)

    logger.info(f"Iniciando solicitud paginada para '{action_name_for_log}' desde '{url_base.split('?')[0]}...'. "
                f"Max total: {max_items_total}, por página: {top_value}, max_páginas: {max_pages_to_fetch}")
    try:
        while current_url and len(all_items) < max_items_total and page_count < max_pages_to_fetch:
            page_count += 1
            # Los parámetros de query ($top, $select, etc.) solo se aplican a la primera llamada.
            # Las llamadas subsecuentes usan el @odata.nextLink completo.
            is_first_call = (page_count == 1)
            
            logger.debug(f"Página {page_count} para '{action_name_for_log}': GET {current_url.split('?')[0]}...")
            
            response = client.get(
                url=current_url, 
                scope=scope, 
                # Pasar params solo si es la primera llamada y la URL es la base, 
                # ya que @odata.nextLink ya contiene los parámetros.
                params=query_api_params_initial if is_first_call and current_url == url_base else None
            )
            response_data = response.json()
            
            page_items = response_data.get('value', [])
            if not isinstance(page_items, list):
                logger.warning(f"Respuesta inesperada para '{action_name_for_log}', la clave 'value' no es una lista: {response_data}")
                break # Salir si el formato de respuesta no es el esperado
            
            for item in page_items:
                if len(all_items) < max_items_total:
                    all_items.append(item)
                else:
                    break # Alcanzado el límite de max_items_total
            
            current_url = response_data.get('@odata.nextLink')
            if not current_url or len(all_items) >= max_items_total:
                logger.debug(f"'{action_name_for_log}': Fin de paginación. nextLink: {'Sí' if current_url else 'No'}, Items actuales: {len(all_items)}.")
                break
        
        if page_count >= max_pages_to_fetch and current_url:
            logger.warning(f"'{action_name_for_log}' alcanzó el límite de {max_pages_to_fetch} páginas procesadas. Puede haber más resultados no recuperados.")

        logger.info(f"'{action_name_for_log}' recuperó {len(all_items)} items en {page_count} páginas.")
        return {"status": "success", "data": all_items, "total_retrieved": len(all_items), "pages_processed": page_count}
    except Exception as e:
        # Usar params_input aquí para el logging del error, ya que contiene los parámetros originales.
        return _handle_email_api_error(e, action_name_for_log, params_input)


# ---- Helper Interno para Normalizar Destinatarios ----
def _normalize_recipients(
    rec_input: Optional[Union[str, List[str], List[Dict[str, Any]]]],
    type_name: str = "destinatario" # Usado para logging, ej. "destinatario", "cc", "bcc"
) -> List[Dict[str, Any]]:
    """
    Normaliza la entrada de destinatarios a una lista de diccionarios de Graph API.
    Acepta:
    - Un string con emails separados por comas o punto y coma.
    - Una lista de strings de emails.
    - Una lista de dicts ya en formato Graph API (ej. {"emailAddress": {"address": "..."}}).
    """
    recipients_list: List[Dict[str, Any]] = []
    if rec_input is None: # Tratar None explícitamente para evitar errores con isinstance
        return recipients_list

    input_list_to_process: List[Any] = []
    if isinstance(rec_input, str):
        # Dividir por coma o punto y coma, y limpiar espacios
        emails_from_string = [email.strip() for email in rec_input.replace(';', ',').split(',') if email.strip()]
        input_list_to_process.extend(emails_from_string)
    elif isinstance(rec_input, list):
        input_list_to_process = rec_input # Ya es una lista, procesar sus elementos
    else:
        logger.warning(f"Formato de entrada para '{type_name}' es inválido. Se esperaba str o List, pero se recibió {type(rec_input)}. Se ignorará.")
        return [] # Devolver lista vacía, la función que llama debe manejar si esto es un error crítico

    for item in input_list_to_process:
        if isinstance(item, str) and item.strip() and "@" in item: # Es un string de email
            recipients_list.append({"emailAddress": {"address": item.strip()}})
        elif isinstance(item, dict) and \
             isinstance(item.get("emailAddress"), dict) and \
             isinstance(item["emailAddress"].get("address"), str) and \
             item["emailAddress"]["address"].strip() and "@" in item["emailAddress"]["address"]:
            # Ya tiene el formato correcto de Graph API
            recipients_list.append(item)
        else:
            logger.warning(f"Item '{item}' en la lista de '{type_name}' no es un email válido o no tiene el formato Graph esperado. Se ignorará.")
            
    if not recipients_list and rec_input: # Si hubo una entrada pero no se pudo procesar ningún destinatario válido
        logger.warning(f"La entrada proporcionada para '{type_name}' ('{rec_input}') no resultó en destinatarios válidos.")

    return recipients_list

# ---- FUNCIONES DE ACCIÓN PARA CORREO (Nombres alineados con ACTION_MAP) ----

def list_messages(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista mensajes de correo de una carpeta específica."""
    mailbox: str = params.get('mailbox', 'me') # 'me' o userPrincipalName/ID
    folder_id: str = params.get('folder_id', 'Inbox') # ID de la carpeta o well-known name
    
    top_per_page: int = min(int(params.get('top_per_page', 25)), constants.DEFAULT_PAGING_SIZE_MAIL) 
    max_items_total: int = int(params.get('max_items_total', 100))
    
    select_fields: Optional[str] = params.get('select')
    filter_query: Optional[str] = params.get('filter_query')
    order_by: Optional[str] = params.get('order_by', 'receivedDateTime desc') # Default order
    search_query: Optional[str] = params.get('search') # Para usar $search

    # Construir URL base
    if mailbox.lower() == 'me':
        url_base = f"{constants.GRAPH_API_BASE_URL}/me/mailFolders/{folder_id}/messages"
    else:
        url_base = f"{constants.GRAPH_API_BASE_URL}/users/{mailbox}/mailFolders/{folder_id}/messages"
    
    query_api_params: Dict[str, Any] = {'$top': top_per_page}
    if select_fields: 
        query_api_params['$select'] = select_fields
    else: # Un select por defecto útil
        query_api_params['$select'] = "id,receivedDateTime,subject,sender,from,toRecipients,ccRecipients,isRead,hasAttachments,importance,webLink"
    
    if filter_query and not search_query: # $filter y $search no se suelen usar juntos directamente en /messages. $search es más potente.
        query_api_params['$filter'] = filter_query
    elif search_query:
        query_api_params['$search'] = f'"{search_query}"' # Encerrar query entre comillas
        # $orderby no es soportado con $search en /messages; los resultados vienen por relevancia.
        if '$orderby' in query_api_params: 
            del query_api_params['$orderby']
            logger.info("Parámetro '$orderby' ignorado cuando se usa '$search' para listar mensajes.")
    elif order_by: # Solo si no hay $search
        query_api_params['$orderby'] = order_by
    
    return _email_paged_request(client, url_base, GRAPH_SCOPE_MAIL_READ, params, query_api_params, max_items_total, "list_messages")

def get_message(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Obtiene un mensaje de correo específico por su ID."""
    mailbox: str = params.get('mailbox', 'me')
    message_id: Optional[str] = params.get('message_id')
    
    select_fields: Optional[str] = params.get('select')
    expand_fields: Optional[str] = params.get('expand') # Ej: "attachments", "singleValueExtendedProperties($filter=id eq 'String {guid} NameopropName')"

    if not message_id:  
        return _handle_email_api_error(ValueError("'message_id' es un parámetro requerido."), "get_message", params)

    if mailbox.lower() == 'me':
        url = f"{constants.GRAPH_API_BASE_URL}/me/messages/{message_id}"
    else:
        url = f"{constants.GRAPH_API_BASE_URL}/users/{mailbox}/messages/{message_id}"
        
    query_api_params: Dict[str, Any] = {}
    if select_fields: 
        query_api_params['$select'] = select_fields
    else: # Select por defecto generoso
        query_api_params['$select'] = "id,receivedDateTime,subject,sender,from,toRecipients,ccRecipients,bccRecipients,body,bodyPreview,importance,isRead,isDraft,hasAttachments,webLink,conversationId,parentFolderId"

    if expand_fields: 
        query_api_params['$expand'] = expand_fields
    
    logger.info(f"Leyendo correo '{message_id}' para '{mailbox}' (Select: {select_fields or 'default'}, Expand: {expand_fields or 'none'})")
    try:
        response = client.get(url, scope=GRAPH_SCOPE_MAIL_READ, params=query_api_params if query_api_params else None)
        return {"status": "success", "data": response.json()}
    except Exception as e:
        return _handle_email_api_error(e, "get_message", params)

def send_message(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Envía un mensaje de correo electrónico."""
    mailbox: str = params.get('mailbox', 'me') # Quién envía el correo
    
    # Parámetros del mensaje
    destinatarios_to_in = params.get('to_recipients') # Entrada para 'toRecipients'
    asunto: Optional[str] = params.get('subject')
    contenido_cuerpo: Optional[str] = params.get('body_content')
    tipo_cuerpo: str = params.get('body_type', 'HTML').upper() # HTML o TEXT
    
    destinatarios_cc_in = params.get('cc_recipients')
    destinatarios_bcc_in = params.get('bcc_recipients')
    
    # Adjuntos: lista de objetos de adjunto de Graph API
    # Ej: [{"@odata.type": "#microsoft.graph.fileAttachment", "name": "file.txt", "contentBytes": "base64encodedcontent"}]
    attachments_payload: Optional[List[dict]] = params.get('attachments') 
    
    save_to_sent_items: bool = str(params.get('save_to_sent_items', "true")).lower() == "true"

    if not destinatarios_to_in or asunto is None or contenido_cuerpo is None: # asunto y contenido pueden ser vacíos, pero deben estar presentes
        return _handle_email_api_error(ValueError("'to_recipients', 'subject' y 'body_content' son parámetros requeridos."), "send_message", params)
    if tipo_cuerpo not in ["HTML", "TEXT"]:
        return _handle_email_api_error(ValueError("'body_type' debe ser 'HTML' o 'TEXT'."), "send_message", params)

    to_recipients_list = _normalize_recipients(destinatarios_to_in, "to_recipients")
    if not to_recipients_list: 
        return _handle_email_api_error(ValueError("Se requiere al menos un destinatario válido en 'to_recipients'."), "send_message", params)
    
    cc_recipients_list = _normalize_recipients(destinatarios_cc_in, "cc_recipients")
    bcc_recipients_list = _normalize_recipients(destinatarios_bcc_in, "bcc_recipients")

    # Construcción del objeto 'message' para el payload de sendMail
    message_object: Dict[str, Any] = {
        "subject": asunto,
        "body": {"contentType": tipo_cuerpo, "content": contenido_cuerpo},
        "toRecipients": to_recipients_list
    }
    if cc_recipients_list: message_object["ccRecipients"] = cc_recipients_list
    if bcc_recipients_list: message_object["bccRecipients"] = bcc_recipients_list
    if attachments_payload and isinstance(attachments_payload, list):
        message_object["attachments"] = attachments_payload
    
    # Payload final para el endpoint /sendMail
    final_sendmail_payload = {"message": message_object, "saveToSentItems": save_to_sent_items }
    
    if mailbox.lower() == 'me':
        url = f"{constants.GRAPH_API_BASE_URL}/me/sendMail"
    else:
        url = f"{constants.GRAPH_API_BASE_URL}/users/{mailbox}/sendMail"
        
    logger.info(f"Intentando enviar correo desde '{mailbox}'. Asunto: '{asunto}'")
    try:
        # El endpoint /sendMail no crea un borrador, envía directamente. Devuelve 202 Accepted.
        response = client.post(url, scope=GRAPH_SCOPE_MAIL_SEND, json_data=final_sendmail_payload)
        # No hay cuerpo en la respuesta para 202
        return {"status": "success", "message": "Solicitud de envío de correo aceptada por el servidor.", "http_status": response.status_code}
    except Exception as e:
        return _handle_email_api_error(e, "send_message", params)

def reply_message(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Responde a un mensaje de correo existente."""
    mailbox: str = params.get('mailbox', 'me')
    message_id: Optional[str] = params.get('message_id') # ID del mensaje al que se responde
    comment_content: Optional[str] = params.get('comment') # Contenido del cuerpo de la respuesta
    
    # Permite anular o añadir destinatarios, cc, bcc, o adjuntos a la respuesta
    message_payload_override: Optional[Dict[str, Any]] = params.get("message_payload_override") 

    if not message_id or comment_content is None: # comment_content puede ser vacío, pero debe estar presente
        return _handle_email_api_error(ValueError("'message_id' y 'comment' son parámetros requeridos."), "reply_message", params)

    action_url_segment = "reply" # Para /reply
    url: str
    if mailbox.lower() == 'me':
        url = f"{constants.GRAPH_API_BASE_URL}/me/messages/{message_id}/{action_url_segment}"
    else:
        url = f"{constants.GRAPH_API_BASE_URL}/users/{mailbox}/messages/{message_id}/{action_url_segment}"
    
    payload_reply: Dict[str, Any] = {"comment": comment_content}
    if message_payload_override and isinstance(message_payload_override, dict):
        payload_reply["message"] = message_payload_override # ej: {"toRecipients": [...], "attachments": [...]}
    
    logger.info(f"Respondiendo al correo '{message_id}' para '{mailbox}'")
    try:
        # La acción reply/replyAll devuelve 202 Accepted.
        response = client.post(url, scope=GRAPH_SCOPE_MAIL_SEND, json_data=payload_reply)
        return {"status": "success", "message": "Solicitud de respuesta de correo aceptada.", "http_status": response.status_code}
    except Exception as e:
        return _handle_email_api_error(e, "reply_message", params)

def forward_message(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Reenvía un mensaje de correo existente."""
    mailbox: str = params.get('mailbox', 'me')
    message_id: Optional[str] = params.get('message_id') # ID del mensaje a reenviar
    
    destinatarios_to_in = params.get('to_recipients') # Nuevos destinatarios del reenvío
    comment_content: str = params.get('comment', "") # Comentario opcional para el cuerpo del mensaje de reenvío
    
    # Permite anular o añadir cc, bcc, o adjuntos al mensaje reenviado
    message_payload_override: Optional[Dict[str, Any]] = params.get("message_payload_override")

    if not message_id or not destinatarios_to_in:
        return _handle_email_api_error(ValueError("'message_id' y 'to_recipients' son parámetros requeridos."), "forward_message", params)

    to_recipients_list = _normalize_recipients(destinatarios_to_in, "to_recipients (reenvío)")
    if not to_recipients_list:
        return _handle_email_api_error(ValueError("Se requiere al menos un destinatario válido en 'to_recipients' para reenviar."), "forward_message", params)

    url: str
    if mailbox.lower() == 'me':
        url = f"{constants.GRAPH_API_BASE_URL}/me/messages/{message_id}/forward"
    else:
        url = f"{constants.GRAPH_API_BASE_URL}/users/{mailbox}/messages/{message_id}/forward"
        
    payload_forward: Dict[str, Any] = {"toRecipients": to_recipients_list, "comment": comment_content}
    if message_payload_override and isinstance(message_payload_override, dict):
        payload_forward["message"] = message_payload_override # ej: {"attachments": [...]}
    
    logger.info(f"Reenviando correo '{message_id}' para '{mailbox}' a {len(to_recipients_list)} destinatario(s)")
    try:
        # La acción forward devuelve 202 Accepted.
        response = client.post(url, scope=GRAPH_SCOPE_MAIL_SEND, json_data=payload_forward)
        return {"status": "success", "message": "Solicitud de reenvío de correo aceptada.", "http_status": response.status_code}
    except Exception as e:
        return _handle_email_api_error(e, "forward_message", params)

def delete_message(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Elimina un mensaje de correo (lo mueve a la carpeta de Elementos Eliminados)."""
    mailbox: str = params.get('mailbox', 'me')
    message_id: Optional[str] = params.get('message_id')
    if not message_id:
        return _handle_email_api_error(ValueError("'message_id' es un parámetro requerido."), "delete_message", params)

    if mailbox.lower() == 'me':
        url = f"{constants.GRAPH_API_BASE_URL}/me/messages/{message_id}"
    else:
        url = f"{constants.GRAPH_API_BASE_URL}/users/{mailbox}/messages/{message_id}"
        
    logger.info(f"Eliminando correo '{message_id}' para '{mailbox}' (moviendo a Elementos Eliminados)")
    try:
        # DELETE en un mensaje devuelve 204 No Content.
        response = client.delete(url, scope=GRAPH_SCOPE_MAIL_READ_WRITE)
        return {"status": "success", "message": "Correo movido a elementos eliminados exitosamente.", "http_status": response.status_code}
    except Exception as e:
        return _handle_email_api_error(e, "delete_message", params)

def move_message(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Mueve un mensaje de correo a una carpeta de destino específica."""
    mailbox: str = params.get('mailbox', 'me')
    message_id: Optional[str] = params.get('message_id')
    destination_folder_id: Optional[str] = params.get('destination_folder_id') # ID de la carpeta destino

    if not message_id or not destination_folder_id:
        return _handle_email_api_error(ValueError("'message_id' y 'destination_folder_id' son parámetros requeridos."), "move_message", params)

    if mailbox.lower() == 'me':
        url = f"{constants.GRAPH_API_BASE_URL}/me/messages/{message_id}/move"
    else:
        url = f"{constants.GRAPH_API_BASE_URL}/users/{mailbox}/messages/{message_id}/move"
        
    body_payload = {"destinationId": destination_folder_id}
    logger.info(f"Moviendo correo '{message_id}' para '{mailbox}' a carpeta '{destination_folder_id}'")
    try:
        # La acción move devuelve el objeto Message movido (200 OK o 201 Created, según la doc).
        response = client.post(url, scope=GRAPH_SCOPE_MAIL_READ_WRITE, json_data=body_payload) 
        return {"status": "success", "data": response.json(), "message": "Correo movido exitosamente."}
    except Exception as e:
        return _handle_email_api_error(e, "move_message", params)

def list_folders(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista las carpetas de correo."""
    mailbox: str = params.get('mailbox', 'me')
    # Para listar subcarpetas de una carpeta específica:
    parent_folder_id: Optional[str] = params.get('parent_folder_id') 
    
    top_per_page: int = min(int(params.get('top_per_page', 25)), constants.DEFAULT_PAGING_SIZE)
    max_items_total: int = int(params.get('max_items_total', 100))
    
    select_fields: Optional[str] = params.get('select')
    filter_query: Optional[str] = params.get('filter_query')
    # include_hidden_folders: bool = str(params.get('include_hidden_folders', "false")).lower() == "true" # Parámetro específico de API, no OData estándar.

    url_base: str
    if mailbox.lower() == 'me':
        if parent_folder_id:
            url_base = f"{constants.GRAPH_API_BASE_URL}/me/mailFolders/{parent_folder_id}/childFolders"
        else: # Carpetas raíz
            url_base = f"{constants.GRAPH_API_BASE_URL}/me/mailFolders"
    else: # Buzón de otro usuario
        if parent_folder_id:
            url_base = f"{constants.GRAPH_API_BASE_URL}/users/{mailbox}/mailFolders/{parent_folder_id}/childFolders"
        else:
            url_base = f"{constants.GRAPH_API_BASE_URL}/users/{mailbox}/mailFolders"
            
    query_api_params: Dict[str, Any] = {'$top': top_per_page}
    if select_fields: 
        query_api_params['$select'] = select_fields
    else: # Select por defecto
        query_api_params['$select'] = "id,displayName,parentFolderId,childFolderCount,unreadItemCount,totalItemCount,isHidden" # isHidden si soportado
    
    if filter_query: 
        query_api_params['$filter'] = filter_query
    
    # El parámetro 'includeHiddenFolders' no es un OData estándar, se pasa como query param directo si la API lo soporta.
    # if include_hidden_folders: query_api_params['includeHiddenFolders'] = 'true' 
    # Consultar documentación de Graph API para /mailFolders si soporta este u otros parámetros no OData.
    
    log_context = f"carpetas para '{mailbox}'"
    if parent_folder_id: log_context += f" bajo '{parent_folder_id}'"
    return _email_paged_request(client, url_base, GRAPH_SCOPE_MAIL_READ, params, query_api_params, max_items_total, f"list_folders ({log_context})")

def create_folder(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Crea una nueva carpeta de correo."""
    mailbox: str = params.get('mailbox', 'me')
    folder_name: Optional[str] = params.get('folder_name') # Nombre para la nueva carpeta (displayName)
    parent_folder_id: Optional[str] = params.get('parent_folder_id') # ID de la carpeta padre; si es None/vacío, se crea en la raíz de mailFolders.

    if not folder_name:
        return _handle_email_api_error(ValueError("'folder_name' es un parámetro requerido."), "create_folder", params)

    body_payload = {"displayName": folder_name}
    # Se pueden añadir más propiedades como 'isHidden' si la API lo permite.
    # if params.get('is_hidden') is not None: body_payload['isHidden'] = bool(params['is_hidden'])
    
    url: str
    log_context_parent = ""
    if parent_folder_id:
        if mailbox.lower() == 'me':
            url = f"{constants.GRAPH_API_BASE_URL}/me/mailFolders/{parent_folder_id}/childFolders"
        else:
            url = f"{constants.GRAPH_API_BASE_URL}/users/{mailbox}/mailFolders/{parent_folder_id}/childFolders"
        log_context_parent = f" bajo carpeta padre '{parent_folder_id}'"
    else: # Crear en la raíz de mailFolders del buzón
        if mailbox.lower() == 'me':
            url = f"{constants.GRAPH_API_BASE_URL}/me/mailFolders"
        else:
            url = f"{constants.GRAPH_API_BASE_URL}/users/{mailbox}/mailFolders"
            
    logger.info(f"Creando carpeta de correo '{folder_name}' para '{mailbox}'{log_context_parent}")
    try:
        # Crear una mailFolder devuelve el objeto de carpeta creado (201 Created).
        response = client.post(url, scope=GRAPH_SCOPE_MAIL_READ_WRITE, json_data=body_payload) 
        return {"status": "success", "data": response.json(), "message": "Carpeta de correo creada exitosamente."}
    except Exception as e:
        return _handle_email_api_error(e, "create_folder", params)

def search_messages(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Busca mensajes de correo en el buzón del usuario o en un buzón específico."""
    # Esta función es muy similar a list_messages cuando se usa el parámetro '$search'.
    # Se mantiene por claridad semántica si el usuario quiere "buscar" en lugar de "listar con filtro de búsqueda".
    mailbox: str = params.get('mailbox', 'me')
    search_query_kql: Optional[str] = params.get('query') # Cadena de búsqueda, preferiblemente en formato KQL para $search
    
    if not search_query_kql:
        return _handle_email_api_error(ValueError("'query' de búsqueda es un parámetro requerido."), "search_messages", params)

    # Reutilizar list_messages, pasándole el 'search_query_kql' al parámetro 'search' de list_messages.
    list_params = params.copy() # Copiar para no modificar los params originales
    list_params['search'] = search_query_kql # Asignar el query al parámetro 'search' que espera list_messages
    if 'query' in list_params: del list_params['query'] # Eliminar 'query' si existe para evitar confusión en list_messages

    logger.info(f"Iniciando búsqueda de mensajes (wrapper para list_messages con $search) para '{mailbox}' con query: '{search_query_kql}'")
    return list_messages(client, list_params)


# ---- Funciones NO mapeadas por el script (se mantienen con prefijo 'email_') ----

def email_create_draft(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Crea un nuevo mensaje de correo como borrador."""
    mailbox: str = params.get('mailbox', 'me')
    
    # Parámetros del mensaje borrador (similares a send_message pero sin saveToSentItems)
    destinatarios_to_in = params.get('to_recipients')
    asunto: Optional[str] = params.get('subject', "") # Asunto puede ser vacío para borradores
    contenido_cuerpo: Optional[str] = params.get('body_content', "") # Cuerpo puede ser vacío
    tipo_cuerpo: str = params.get('body_type', 'HTML').upper()
    destinatarios_cc_in = params.get('cc_recipients')
    destinatarios_bcc_in = params.get('bcc_recipients')
    attachments_payload: Optional[List[dict]] = params.get('attachments')

    to_recipients_list = _normalize_recipients(destinatarios_to_in, "to_recipients (borrador)")
    cc_recipients_list = _normalize_recipients(destinatarios_cc_in, "cc_recipients (borrador)")
    bcc_recipients_list = _normalize_recipients(destinatarios_bcc_in, "bcc_recipients (borrador)")

    # Construcción del objeto 'message' para crear el borrador
    draft_message_payload: Dict[str, Any] = {
        "subject": asunto,
        "body": {"contentType": tipo_cuerpo, "content": contenido_cuerpo}
    }
    # Añadir destinatarios y adjuntos solo si están presentes
    if to_recipients_list: draft_message_payload["toRecipients"] = to_recipients_list
    if cc_recipients_list: draft_message_payload["ccRecipients"] = cc_recipients_list
    if bcc_recipients_list: draft_message_payload["bccRecipients"] = bcc_recipients_list
    if attachments_payload and isinstance(attachments_payload, list):
        draft_message_payload["attachments"] = attachments_payload

    # Endpoint para crear un mensaje (que por defecto es un borrador si no se envía)
    if mailbox.lower() == 'me':
        url = f"{constants.GRAPH_API_BASE_URL}/me/messages"
    else:
        url = f"{constants.GRAPH_API_BASE_URL}/users/{mailbox}/messages"
        
    logger.info(f"Guardando borrador de correo para '{mailbox}'. Asunto: '{asunto if asunto else '(Sin asunto)'}'")
    try:
        # POST a /messages crea un borrador. Devuelve el objeto Message creado.
        response = client.post(url, scope=GRAPH_SCOPE_MAIL_READ_WRITE, json_data=draft_message_payload) 
        return {"status": "success", "data": response.json(), "message": "Borrador de correo guardado exitosamente."}
    except Exception as e:
        return _handle_email_api_error(e, "email_create_draft", params)

def email_send_draft(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Envía un mensaje de correo que ya existe como borrador."""
    mailbox: str = params.get('mailbox', 'me')
    message_id: Optional[str] = params.get('message_id') # ID del mensaje borrador a enviar

    if not message_id:
        return _handle_email_api_error(ValueError("'message_id' del borrador es un parámetro requerido."), "email_send_draft", params)

    if mailbox.lower() == 'me':
        url = f"{constants.GRAPH_API_BASE_URL}/me/messages/{message_id}/send"
    else:
        url = f"{constants.GRAPH_API_BASE_URL}/users/{mailbox}/messages/{message_id}/send"
        
    logger.info(f"Enviando borrador de correo '{message_id}' para '{mailbox}'")
    try:
        # POST a /send en un mensaje borrador. No requiere cuerpo. Devuelve 202 Accepted.
        response = client.post(url, scope=GRAPH_SCOPE_MAIL_SEND) 
        return {"status": "success", "message": "Solicitud de envío de borrador aceptada por el servidor.", "http_status": response.status_code}
    except Exception as e:
        return _handle_email_api_error(e, "email_send_draft", params)

# --- FIN DEL MÓDULO actions/correo_actions.py ---