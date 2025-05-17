# MyHttpTrigger/actions/teams_actions.py
import logging
import requests # Para requests.exceptions.HTTPError
import json
from typing import Dict, List, Optional, Any, Union

# Importar el cliente autenticado y las constantes
from shared.helpers.http_client import AuthenticatedHttpClient
from shared import constants

logger = logging.getLogger(__name__)

# --- Constantes de Scopes para Microsoft Teams (a definir en constants.py idealmente) ---
# Si no están en constants.py, usamos el GRAPH_SCOPE general y advertimos.
GRAPH_SCOPE_TEAMS_READ_BASIC_ALL = getattr(constants, 'GRAPH_SCOPE_TEAMS_READ_BASIC_ALL', constants.GRAPH_SCOPE)
GRAPH_SCOPE_CHANNEL_READ_ALL = getattr(constants, 'GRAPH_SCOPE_CHANNEL_READ_ALL', constants.GRAPH_SCOPE)
GRAPH_SCOPE_CHANNEL_MESSAGE_SEND = getattr(constants, 'GRAPH_SCOPE_CHANNEL_MESSAGE_SEND', constants.GRAPH_SCOPE)
GRAPH_SCOPE_CHAT_READ_WRITE = getattr(constants, 'GRAPH_SCOPE_CHAT_READ_WRITE', constants.GRAPH_SCOPE)
GRAPH_SCOPE_CHAT_SEND = getattr(constants, 'GRAPH_SCOPE_CHAT_SEND', constants.GRAPH_SCOPE) # O Chat.ReadWrite
GRAPH_SCOPE_ONLINE_MEETINGS_READ_WRITE = getattr(constants, 'GRAPH_SCOPE_ONLINE_MEETINGS_READ_WRITE', constants.GRAPH_SCOPE)
GRAPH_SCOPE_GROUP_READ_WRITE_ALL = getattr(constants, 'GRAPH_SCOPE_GROUP_READ_WRITE_ALL', constants.GRAPH_SCOPE) # Para listar miembros

def _log_teams_scope_fallback_warnings():
    scopes_to_check = {
        "GRAPH_SCOPE_TEAMS_READ_BASIC_ALL": GRAPH_SCOPE_TEAMS_READ_BASIC_ALL,
        "GRAPH_SCOPE_CHANNEL_READ_ALL": GRAPH_SCOPE_CHANNEL_READ_ALL,
        "GRAPH_SCOPE_CHANNEL_MESSAGE_SEND": GRAPH_SCOPE_CHANNEL_MESSAGE_SEND,
        "GRAPH_SCOPE_CHAT_READ_WRITE": GRAPH_SCOPE_CHAT_READ_WRITE,
        "GRAPH_SCOPE_CHAT_SEND": GRAPH_SCOPE_CHAT_SEND,
        "GRAPH_SCOPE_ONLINE_MEETINGS_READ_WRITE": GRAPH_SCOPE_ONLINE_MEETINGS_READ_WRITE,
        "GRAPH_SCOPE_GROUP_READ_WRITE_ALL": GRAPH_SCOPE_GROUP_READ_WRITE_ALL,
    }
    for name, actual_scope_val_list in scopes_to_check.items():
        if actual_scope_val_list and constants.GRAPH_SCOPE and actual_scope_val_list[0] == constants.GRAPH_SCOPE[0] and name != "GRAPH_SCOPE":
            logger.warning(f"Usando GRAPH_SCOPE general para una operación de Teams que podría beneficiarse de '{name}'. Considere definirla en constants.py.")
_log_teams_scope_fallback_warnings()

# --- Helper para manejo de errores de API de Teams/Graph ---
def _handle_teams_api_error(e: Exception, action_name: str, params_for_log: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    # Similar al helper de correo o sharepoint, adaptado para Teams
    log_message = f"Error en Teams action '{action_name}'"
    safe_params = {}
    if params_for_log:
        sensitive_keys = ['message', 'content', 'body', 'payload'] # Claves comunes con contenido
        safe_params = {k: (v if k not in sensitive_keys else "[CONTENIDO OMITIDO]") for k, v in params_for_log.items()}
        log_message += f" con params: {safe_params}"
    
    logger.error(f"{log_message}: {type(e).__name__} - {str(e)}", exc_info=True)
    
    details = str(e)
    status_code = 500
    graph_error_code = None

    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
        status_code = e.response.status_code
        try:
            error_data = e.response.json()
            error_info = error_data.get("error", {})
            details = error_info.get("message", e.response.text)
            graph_error_code = error_info.get("code")
        except json.JSONDecodeError:
            details = e.response.text
            
    return {
        "status": "error", "action": action_name,
        "message": f"Error ejecutando {action_name}: {type(e).__name__}",
        "http_status": status_code, "details": details, "graph_error_code": graph_error_code
    }

# --- Helper común para paginación (adaptado para Teams) ---
def _teams_paged_request(
    client: AuthenticatedHttpClient, url_base: str, scope: List[str],
    params_input: Dict[str, Any], query_api_params_initial: Dict[str, Any],
    max_items_total: int, action_name_for_log: str
) -> Dict[str, Any]:
    all_items: List[Dict[str, Any]] = []
    current_url: Optional[str] = url_base
    page_count = 0
    max_pages_to_fetch = constants.MAX_PAGING_PAGES
    top_value = query_api_params_initial.get('$top', constants.DEFAULT_PAGING_SIZE)

    logger.info(f"Iniciando solicitud paginada para '{action_name_for_log}' desde '{url_base.split('?')[0]}...'. Max total: {max_items_total}, por pág: {top_value}, max_págs: {max_pages_to_fetch}")
    try:
        while current_url and len(all_items) < max_items_total and page_count < max_pages_to_fetch:
            page_count += 1
            is_first_call = (page_count == 1 and current_url == url_base)
            current_call_params = query_api_params_initial if is_first_call else None
            
            logger.debug(f"Página {page_count} para '{action_name_for_log}': GET {current_url.split('?')[0]} con params: {current_call_params}")
            response = client.get(url=current_url, scope=scope, params=current_call_params)
            response_data = response.json()
            
            page_items = response_data.get('value', [])
            if not isinstance(page_items, list): break
            
            for item in page_items:
                if len(all_items) < max_items_total: all_items.append(item)
                else: break
            
            current_url = response_data.get('@odata.nextLink')
            if not current_url or len(all_items) >= max_items_total: break
        
        logger.info(f"'{action_name_for_log}' recuperó {len(all_items)} items en {page_count} páginas.")
        return {"status": "success", "data": {"value": all_items, "@odata.count": len(all_items)}, "total_retrieved": len(all_items), "pages_processed": page_count}
    except Exception as e:
        return _handle_teams_api_error(e, action_name_for_log, params_input)

# ---- ACCIONES PARA EQUIPOS (Teams) ----
def list_joined_teams(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista los equipos a los que el usuario autenticado se ha unido."""
    url_base = f"{constants.GRAPH_API_BASE_URL}/me/joinedTeams"
    
    top_per_page: int = min(int(params.get('top_per_page', 25)), constants.DEFAULT_PAGING_SIZE)
    max_items_total: int = int(params.get('max_items_total', 100))
    select_fields: Optional[str] = params.get('select')
    filter_query: Optional[str] = params.get('filter_query') # Ej: "startswith(displayName, 'Contoso')"

    query_api_params: Dict[str, Any] = {'$top': top_per_page}
    if select_fields: query_api_params['$select'] = select_fields
    else: query_api_params['$select'] = "id,displayName,description,isArchived,webUrl"
    if filter_query: query_api_params['$filter'] = filter_query
    
    return _teams_paged_request(client, url_base, GRAPH_SCOPE_TEAMS_READ_BASIC_ALL, params, query_api_params, max_items_total, "list_joined_teams")

def get_team(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Obtiene los detalles de un equipo específico por su ID."""
    team_id: Optional[str] = params.get("team_id")
    if not team_id:
        return _handle_teams_api_error(ValueError("'team_id' es requerido."), "get_team", params)
        
    url = f"{constants.GRAPH_API_BASE_URL}/teams/{team_id}"
    select_fields: Optional[str] = params.get("select")
    query_params = {'$select': select_fields} if select_fields else None
    
    logger.info(f"Obteniendo detalles del equipo '{team_id}' (Select: {select_fields or 'default'})")
    try:
        response = client.get(url, scope=GRAPH_SCOPE_TEAMS_READ_BASIC_ALL, params=query_params)
        return {"status": "success", "data": response.json()}
    except Exception as e:
        return _handle_teams_api_error(e, "get_team", params)

# ---- ACCIONES PARA CANALES (Channels) ----
def list_channels(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista los canales de un equipo específico."""
    team_id: Optional[str] = params.get("team_id")
    if not team_id:
        return _handle_teams_api_error(ValueError("'team_id' es requerido."), "list_channels", params)
        
    url_base = f"{constants.GRAPH_API_BASE_URL}/teams/{team_id}/channels"
    
    top_per_page: int = min(int(params.get('top_per_page', 25)), constants.DEFAULT_PAGING_SIZE)
    max_items_total: int = int(params.get('max_items_total', 100))
    select_fields: Optional[str] = params.get('select')
    filter_query: Optional[str] = params.get('filter_query')

    query_api_params: Dict[str, Any] = {'$top': top_per_page}
    if select_fields: query_api_params['$select'] = select_fields
    else: query_api_params['$select'] = "id,displayName,description,webUrl,email,membershipType"
    if filter_query: query_api_params['$filter'] = filter_query
    
    return _teams_paged_request(client, url_base, GRAPH_SCOPE_CHANNEL_READ_ALL, params, query_api_params, max_items_total, f"list_channels (team: {team_id})")

def get_channel(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Obtiene los detalles de un canal específico dentro de un equipo."""
    team_id: Optional[str] = params.get("team_id")
    channel_id: Optional[str] = params.get("channel_id")
    if not team_id or not channel_id:
        return _handle_teams_api_error(ValueError("'team_id' y 'channel_id' son requeridos."), "get_channel", params)

    url = f"{constants.GRAPH_API_BASE_URL}/teams/{team_id}/channels/{channel_id}"
    select_fields: Optional[str] = params.get("select")
    query_params = {'$select': select_fields} if select_fields else None
    
    logger.info(f"Obteniendo detalles del canal '{channel_id}' en equipo '{team_id}'")
    try:
        response = client.get(url, scope=GRAPH_SCOPE_CHANNEL_READ_ALL, params=query_params)
        return {"status": "success", "data": response.json()}
    except Exception as e:
        return _handle_teams_api_error(e, "get_channel", params)

def send_channel_message(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Envía un mensaje a un canal específico."""
    team_id: Optional[str] = params.get("team_id")
    channel_id: Optional[str] = params.get("channel_id")
    message_content: Optional[str] = params.get("content") # Contenido del mensaje (HTML o text)
    content_type: str = params.get("content_type", "HTML").upper() # HTML o TEXT

    if not team_id or not channel_id or message_content is None:
        return _handle_teams_api_error(ValueError("'team_id', 'channel_id' y 'content' son requeridos."), "send_channel_message", params)
    if content_type not in ["HTML", "TEXT"]:
        return _handle_teams_api_error(ValueError("'content_type' debe ser HTML o TEXT."), "send_channel_message", params)

    url = f"{constants.GRAPH_API_BASE_URL}/teams/{team_id}/channels/{channel_id}/messages"
    payload = {
        "body": {
            "contentType": content_type,
            "content": message_content
        }
    }
    # Otros campos: subject, attachments, mentions, etc.
    if params.get("subject"): payload["subject"] = params["subject"]
    
    logger.info(f"Enviando mensaje al canal '{channel_id}' del equipo '{team_id}'")
    try:
        response = client.post(url, scope=GRAPH_SCOPE_CHANNEL_MESSAGE_SEND, json_data=payload)
        return {"status": "success", "data": response.json(), "message": "Mensaje enviado al canal."}
    except Exception as e:
        return _handle_teams_api_error(e, "send_channel_message", params)

def list_channel_messages(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista los mensajes de un canal, incluyendo respuestas (si se expande)."""
    team_id: Optional[str] = params.get("team_id")
    channel_id: Optional[str] = params.get("channel_id")
    if not team_id or not channel_id:
        return _handle_teams_api_error(ValueError("'team_id' y 'channel_id' son requeridos."), "list_channel_messages", params)

    url_base = f"{constants.GRAPH_API_BASE_URL}/teams/{team_id}/channels/{channel_id}/messages"
    
    top_per_page: int = min(int(params.get('top_per_page', 25)), 50) # Max $top para mensajes es 50
    max_items_total: int = int(params.get('max_items_total', 100))
    select_fields: Optional[str] = params.get('select')
    # filter_query: Optional[str] = params.get('filter_query') # $filter tiene limitaciones en mensajes
    # order_by: Optional[str] = params.get('order_by') # $orderby tiene limitaciones
    expand_replies: bool = str(params.get('expand_replies', "false")).lower() == "true"


    query_api_params: Dict[str, Any] = {'$top': top_per_page}
    if select_fields: query_api_params['$select'] = select_fields
    else: query_api_params['$select'] = "id,subject,summary,body,from,createdDateTime,lastModifiedDateTime,importance,webUrl"
    if expand_replies: query_api_params['$expand'] = "replies"
    
    action_log_name = f"list_channel_messages (team: {team_id}, channel: {channel_id})"
    return _teams_paged_request(client, url_base, GRAPH_SCOPE_CHANNEL_READ_ALL, params, query_api_params, max_items_total, action_log_name)

def reply_to_message(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Envía una respuesta a un mensaje específico en un canal."""
    team_id: Optional[str] = params.get("team_id")
    channel_id: Optional[str] = params.get("channel_id")
    message_id: Optional[str] = params.get("message_id") # ID del mensaje al que se responde
    reply_content: Optional[str] = params.get("content")
    content_type: str = params.get("content_type", "HTML").upper()

    if not team_id or not channel_id or not message_id or reply_content is None:
        return _handle_teams_api_error(ValueError("'team_id', 'channel_id', 'message_id' y 'content' son requeridos."), "reply_to_message", params)

    url = f"{constants.GRAPH_API_BASE_URL}/teams/{team_id}/channels/{channel_id}/messages/{message_id}/replies"
    payload = {
        "body": {
            "contentType": content_type,
            "content": reply_content
        }
    }
    logger.info(f"Enviando respuesta al mensaje '{message_id}' en canal '{channel_id}', equipo '{team_id}'")
    try:
        response = client.post(url, scope=GRAPH_SCOPE_CHANNEL_MESSAGE_SEND, json_data=payload)
        return {"status": "success", "data": response.json(), "message": "Respuesta enviada."}
    except Exception as e:
        return _handle_teams_api_error(e, "reply_to_message", params)

# ---- ACCIONES PARA CHATS (1:1 y grupales) ----
def list_chats(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista los chats del usuario autenticado."""
    url_base = f"{constants.GRAPH_API_BASE_URL}/me/chats"
    
    top_per_page: int = min(int(params.get('top_per_page', 25)), 50) # Max para chats es 50
    max_items_total: int = int(params.get('max_items_total', 100))
    select_fields: Optional[str] = params.get('select')
    filter_query: Optional[str] = params.get('filter_query') # Ej: "topic eq 'My Chat Topic'" o "chatType eq 'group'"
    expand_members: bool = str(params.get('expand_members', "false")).lower() == "true"


    query_api_params: Dict[str, Any] = {'$top': top_per_page}
    if select_fields: query_api_params['$select'] = select_fields
    else: query_api_params['$select'] = "id,topic,chatType,createdDateTime,lastUpdatedDateTime,webUrl"
    if filter_query: query_api_params['$filter'] = filter_query
    if expand_members: query_api_params['$expand'] = "members"
        
    return _teams_paged_request(client, url_base, GRAPH_SCOPE_CHAT_READ_WRITE, params, query_api_params, max_items_total, "list_chats")

def get_chat(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Obtiene los detalles de un chat específico por su ID."""
    chat_id: Optional[str] = params.get("chat_id")
    if not chat_id:
        return _handle_teams_api_error(ValueError("'chat_id' es requerido."), "get_chat", params)
        
    url = f"{constants.GRAPH_API_BASE_URL}/chats/{chat_id}"
    select_fields: Optional[str] = params.get("select")
    expand_members: bool = str(params.get('expand_members', "false")).lower() == "true"
    
    query_api_params: Dict[str, Any] = {}
    if select_fields: query_api_params['$select'] = select_fields
    if expand_members: query_api_params['$expand'] = "members"
    
    logger.info(f"Obteniendo detalles del chat '{chat_id}'")
    try:
        response = client.get(url, scope=GRAPH_SCOPE_CHAT_READ_WRITE, params=query_api_params if query_api_params else None)
        return {"status": "success", "data": response.json()}
    except Exception as e:
        return _handle_teams_api_error(e, "get_chat", params)

def create_chat(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Crea un nuevo chat (1:1 o grupal)."""
    chat_type: str = params.get("chat_type", "group").lower() # "oneOnOne" o "group"
    members_payload: Optional[List[Dict[str, Any]]] = params.get("members") # Lista de miembros como [{"@odata.type": "#microsoft.graph.aadUserConversationMember", "roles": ["owner"], "user@odata.bind": "https://graph.microsoft.com/v1.0/users/GUID"}]
    topic: Optional[str] = params.get("topic") # Requerido para chats grupales

    if not members_payload or not isinstance(members_payload, list) or len(members_payload) < (1 if chat_type == "oneonone" else 2):
        return _handle_teams_api_error(ValueError(f"'members' (lista) es requerido con al menos {'1 (oneOnOne)' if chat_type == 'oneonone' else '2 (group)'} miembros."), "create_chat", params)
    if chat_type == "group" and not topic:
        return _handle_teams_api_error(ValueError("'topic' es requerido para chats grupales."), "create_chat", params)
    if chat_type not in ["oneonone", "group"]:
        return _handle_teams_api_error(ValueError("'chat_type' debe ser 'oneOnOne' o 'group'."), "create_chat", params)

    url = f"{constants.GRAPH_API_BASE_URL}/chats"
    payload: Dict[str, Any] = {"chatType": chat_type, "members": members_payload}
    if chat_type == "group" and topic:
        payload["topic"] = topic
    
    logger.info(f"Creando chat tipo '{chat_type}'" + (f" con tópico '{topic}'" if topic else ""))
    try:
        response = client.post(url, scope=GRAPH_SCOPE_CHAT_READ_WRITE, json_data=payload)
        return {"status": "success", "data": response.json(), "message": "Chat creado."}
    except Exception as e:
        return _handle_teams_api_error(e, "create_chat", params)

def send_chat_message(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Envía un mensaje a un chat existente."""
    chat_id: Optional[str] = params.get("chat_id")
    message_content: Optional[str] = params.get("content")
    content_type: str = params.get("content_type", "HTML").upper()

    if not chat_id or message_content is None:
        return _handle_teams_api_error(ValueError("'chat_id' y 'content' son requeridos."), "send_chat_message", params)

    url = f"{constants.GRAPH_API_BASE_URL}/chats/{chat_id}/messages"
    payload = {
        "body": {
            "contentType": content_type,
            "content": message_content
        }
    }
    logger.info(f"Enviando mensaje al chat '{chat_id}'")
    try:
        response = client.post(url, scope=GRAPH_SCOPE_CHAT_SEND, json_data=payload)
        return {"status": "success", "data": response.json(), "message": "Mensaje enviado al chat."}
    except Exception as e:
        return _handle_teams_api_error(e, "send_chat_message", params)

def list_chat_messages(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista los mensajes de un chat específico."""
    chat_id: Optional[str] = params.get("chat_id")
    if not chat_id:
        return _handle_teams_api_error(ValueError("'chat_id' es requerido."), "list_chat_messages", params)

    url_base = f"{constants.GRAPH_API_BASE_URL}/chats/{chat_id}/messages"
    
    top_per_page: int = min(int(params.get('top_per_page', 25)), 50)
    max_items_total: int = int(params.get('max_items_total', 100))
    select_fields: Optional[str] = params.get('select')
    # filter_query: Optional[str] = params.get('filter_query') # Limitado
    # order_by: Optional[str] = params.get('order_by') # Limitado

    query_api_params: Dict[str, Any] = {'$top': top_per_page}
    if select_fields: query_api_params['$select'] = select_fields
    else: query_api_params['$select'] = "id,subject,body,from,createdDateTime,lastModifiedDateTime,importance,webUrl"
    
    action_log_name = f"list_chat_messages (chat: {chat_id})"
    return _teams_paged_request(client, url_base, GRAPH_SCOPE_CHAT_READ_WRITE, params, query_api_params, max_items_total, action_log_name)

# ---- ACCIONES PARA REUNIONES (Meetings) ----
def schedule_meeting(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Programa una nueva reunión online (evento de calendario con enlace de Teams)."""
    subject: Optional[str] = params.get("subject")
    start_datetime_str: Optional[str] = params.get("start_datetime") # ISO 8601 String
    end_datetime_str: Optional[str] = params.get("end_datetime")   # ISO 8601 String
    timezone: Optional[str] = params.get("timezone", "UTC") # Ej: "Pacific Standard Time"
    attendees_payload: Optional[List[Dict[str, Any]]] = params.get("attendees") # Lista de {"emailAddress": {"address": "...", "name": "..."}, "type": "required/optional/resource"}
    body_content: Optional[str] = params.get("body_content")
    body_type: str = params.get("body_type", "HTML").upper()
    # is_online_meeting y online_meeting_provider son clave para reunión de Teams
    # allow_new_time_proposals: Optional[bool] = params.get("allow_new_time_proposals")

    if not subject or not start_datetime_str or not end_datetime_str:
        return _handle_teams_api_error(ValueError("'subject', 'start_datetime', 'end_datetime' son requeridos."), "schedule_meeting", params)

    try:
        # Validar y formatear fechas (se podría usar el helper de planner/todo si se mueve a shared)
        start_obj = datetime.fromisoformat(start_datetime_str.replace('Z', '+00:00'))
        end_obj = datetime.fromisoformat(end_datetime_str.replace('Z', '+00:00'))
    except ValueError as ve:
        return _handle_teams_api_error(ValueError(f"Formato de fecha inválido: {ve}"), "schedule_meeting", params)

    url = f"{constants.GRAPH_API_BASE_URL}/me/events" # Se crea como un evento en el calendario del usuario
    payload = {
        "subject": subject,
        "start": {"dateTime": start_obj.isoformat(), "timeZone": timezone},
        "end": {"dateTime": end_obj.isoformat(), "timeZone": timezone},
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness" # O "skypeForBusiness", "skypeForConsumer"
    }
    if attendees_payload and isinstance(attendees_payload, list):
        payload["attendees"] = attendees_payload
    if body_content:
        payload["body"] = {"contentType": body_type, "content": body_content}
    # if allow_new_time_proposals is not None:
    #     payload["allowNewTimeProposals"] = allow_new_time_proposals
    
    logger.info(f"Programando reunión de Teams: '{subject}'")
    try:
        response = client.post(url, scope=GRAPH_SCOPE_ONLINE_MEETINGS_READ_WRITE, json_data=payload) # Calendars.ReadWrite también es necesario
        return {"status": "success", "data": response.json(), "message": "Reunión programada."}
    except Exception as e:
        return _handle_teams_api_error(e, "schedule_meeting", params)

def get_meeting_details(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Obtiene los detalles de una reunión online por su ID de evento o enlace de unión."""
    # Esto generalmente se refiere a obtener detalles de un 'event' que es una reunión online.
    # O, si se tiene un 'joinWebUrl', se podría intentar obtener el 'onlineMeeting' asociado.
    event_id: Optional[str] = params.get("event_id") # ID del evento de calendario
    # join_url: Optional[str] = params.get("join_url") # Enlace de unión (más complejo de resolver a un objeto)

    if not event_id: #  and not join_url:
        return _handle_teams_api_error(ValueError("'event_id' es requerido."), "get_meeting_details", params)

    # if event_id:
    url = f"{constants.GRAPH_API_BASE_URL}/me/events/{event_id}"
    # Seleccionar campos relevantes, incluyendo onlineMeeting
    query_params = {'$select': 'id,subject,start,end,organizer,attendees,body,onlineMeeting,webLink'}
    
    logger.info(f"Obteniendo detalles de reunión (evento) '{event_id}'")
    try:
        response = client.get(url, scope=GRAPH_SCOPE_ONLINE_MEETINGS_READ_WRITE, params=query_params) # Calendars.Read
        event_data = response.json()
        # El objeto onlineMeeting contiene joinUrl, conferenceId, etc.
        if not event_data.get("onlineMeeting"):
            return {"status": "warning", "data": event_data, "message": "Evento obtenido, pero no parece ser una reunión online de Teams (falta info de onlineMeeting)."}
        return {"status": "success", "data": event_data}
    except Exception as e:
        return _handle_teams_api_error(e, "get_meeting_details", params)
    # else: // Manejar join_url es más complejo, implica parsear y buscar.
    #    return _handle_teams_api_error(NotImplementedError("Obtener detalles por join_url no implementado directamente."), "get_meeting_details", params)


# ---- ACCIONES PARA MIEMBROS (de Equipos o Chats) ----
def list_members(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """Lista los miembros de un equipo o un chat."""
    team_id: Optional[str] = params.get("team_id")
    chat_id: Optional[str] = params.get("chat_id")

    if not team_id and not chat_id:
        return _handle_teams_api_error(ValueError("Se requiere 'team_id' o 'chat_id'."), "list_members", params)
    if team_id and chat_id:
        return _handle_teams_api_error(ValueError("Proporcione 'team_id' O 'chat_id', no ambos."), "list_members", params)

    parent_type = "equipo" if team_id else "chat"
    parent_id = team_id if team_id else chat_id
    
    url_base: str
    if team_id:
        url_base = f"{constants.GRAPH_API_BASE_URL}/teams/{team_id}/members"
    else: # chat_id
        url_base = f"{constants.GRAPH_API_BASE_URL}/chats/{chat_id}/members"

    top_per_page: int = min(int(params.get('top_per_page', 25)), constants.DEFAULT_PAGING_SIZE)
    max_items_total: int = int(params.get('max_items_total', 100))
    select_fields: Optional[str] = params.get('select')
    filter_query: Optional[str] = params.get('filter_query') # Ej: "startswith(displayName, 'A')"

    query_api_params: Dict[str, Any] = {'$top': top_per_page}
    if select_fields: query_api_params['$select'] = select_fields
    else: query_api_params['$select'] = "id,displayName,userId,email,roles" # roles para miembros de equipo/chat
    if filter_query: query_api_params['$filter'] = filter_query
    
    action_log_name = f"list_members ({parent_type}: {parent_id})"
    # Scope para miembros de equipo: Group.Read.All, Group.ReadWrite.All. Para chat: ChatMember.Read, Chat.ReadWrite.
    scope_to_use = GRAPH_SCOPE_GROUP_READ_WRITE_ALL if team_id else GRAPH_SCOPE_CHAT_READ_WRITE
    return _teams_paged_request(client, url_base, scope_to_use, params, query_api_params, max_items_total, action_log_name)


# --- FIN DEL MÓDULO actions/teams_actions.py ---