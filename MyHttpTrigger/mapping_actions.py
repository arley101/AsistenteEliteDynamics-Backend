# MyHttpTrigger/mapping_actions.py
"""
Archivo central para mapear nombres de acción (strings) a las funciones Python
correspondientes que las ejecutan.
Utiliza importaciones modulares con manejo de errores para permitir carga parcial
si algún módulo de acción tiene problemas o aún no está implementado.
"""

import logging
from typing import Dict, Any, Callable

# Obtener logger
try:
    # Asume que constants.py y APP_NAME están disponibles
    from .shared.constants import APP_NAME
    logger = logging.getLogger(f"{APP_NAME}.mapping_actions")
except ImportError:
    # Fallback si hay problemas con imports iniciales
    logger = logging.getLogger("mapping_actions")
    logger.warning("No se pudo importar APP_NAME desde constantes para el logger de mapeo.")

# Definir un tipo para las funciones de acción
AccionCallable = Callable[[Dict[str, Any], Dict[str, str]], Dict[str, Any]] # Asumiendo que todas devuelven Dict

# Diccionario principal
available_actions: Dict[str, AccionCallable] = {}

# --- Carga de Acciones por Módulo/Servicio ---

# User Profile
try:
    from .actions import user_profile_actions as profile # Importar el módulo renombrado
    available_actions.update({
        # Clave de acción : modulo.funcion_real
        "profile_get_me": profile.get_my_profile,
        "profile_get_manager": profile.get_my_manager,
        "profile_list_directs": profile.list_my_direct_reports,
        # Nota: profile_get_photo devuelve bytes, requiere manejo especial. Omitir por ahora.
    })
    logger.info("Mapeo: Módulo 'user_profile_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'user_profile_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'user_profile_actions': {e}")

# Correo (Outlook)
try:
    from .actions import correo_actions as correo
    available_actions.update({
        "email_list": correo.listar_correos,
        "email_read": correo.leer_correo,
        "email_send": correo.enviar_correo,
        "email_save_draft": correo.guardar_borrador,
        "email_send_draft": correo.enviar_borrador,
        "email_reply": correo.responder_correo,
        "email_forward": correo.reenviar_correo,
        "email_delete": correo.eliminar_correo,
    })
    logger.info("Mapeo: Módulo 'correo_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'correo_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'correo_actions': {e}")

# Calendario (Outlook)
try:
    from .actions import calendario_actions as calendario
    available_actions.update({
        "calendar_list_events": calendario.listar_eventos,
        "calendar_create_event": calendario.crear_evento,
        "calendar_get_event": calendario.obtener_evento,
        "calendar_update_event": calendario.actualizar_evento,
        "calendar_delete_event": calendario.eliminar_evento,
        "calendar_create_teams_meeting": calendario.crear_reunion_teams,
    })
    logger.info("Mapeo: Módulo 'calendario_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'calendario_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'calendario_actions': {e}")

# OneDrive (/me/drive)
try:
    from .actions import onedrive_actions as onedrive
    available_actions.update({
        "onedrive_list_items": onedrive.listar_archivos,
        "onedrive_upload_file": onedrive.subir_archivo,
        # "onedrive_download_file": onedrive.descargar_archivo, # Devuelve bytes
        "onedrive_delete_item": onedrive.eliminar_archivo,
        "onedrive_create_folder": onedrive.crear_carpeta,
        "onedrive_move_item": onedrive.mover_archivo,
        "onedrive_copy_item": onedrive.copiar_archivo, # Async
        "onedrive_get_metadata": onedrive.obtener_metadatos_archivo,
        "onedrive_update_metadata": onedrive.actualizar_metadatos_archivo,
    })
    logger.info("Mapeo: Módulo 'onedrive_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'onedrive_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'onedrive_actions': {e}")

# SharePoint (Listas, Documentos, Memoria)
try:
    from .actions import sharepoint_actions as sp # Usar nombre de archivo correcto
    available_actions.update({
        # Usar claves descriptivas y mapear a nombres de función correctos en sharepoint_actions.py
        "sp_create_list": sp.crear_lista,
        "sp_list_lists": sp.listar_listas,
        "sp_add_list_item": sp.agregar_elemento_lista,
        "sp_list_list_items": sp.listar_elementos_lista,
        "sp_update_list_item": sp.actualizar_elemento_lista,
        "sp_delete_list_item": sp.eliminar_elemento_lista,
        "sp_list_documents": sp.listar_documentos_biblioteca,
        "sp_upload_document": sp.subir_documento,
        "sp_delete_file": sp.eliminar_archivo_biblioteca, # Nombre corregido en el módulo
        "sp_create_folder": sp.crear_carpeta_biblioteca,
        "sp_move_item": sp.mover_archivo_biblioteca, # Nombre corregido en el módulo
        "sp_copy_item": sp.copiar_archivo_biblioteca, # Nombre corregido en el módulo, Async
        "sp_get_metadata": sp.obtener_metadatos_archivo_biblioteca, # Nombre corregido
        "sp_update_metadata": sp.actualizar_metadatos_archivo_biblioteca, # Nombre corregido
        # "sp_get_content": sp.obtener_contenido_archivo_biblioteca, # Devuelve bytes
        "sp_update_content": sp.actualizar_contenido_archivo_biblioteca, # Nombre corregido
        "sp_create_sharing_link": sp.crear_enlace_compartido_archivo_biblioteca, # Nombre corregido
        "sp_memory_save": sp.guardar_dato_memoria,
        "sp_memory_get": sp.recuperar_datos_sesion,
        "sp_memory_delete_key": sp.eliminar_dato_memoria,
        "sp_memory_delete_session": sp.eliminar_memoria_sesion,
        # "sp_export_list": sp.exportar_datos_lista, # Devuelve string/dict
    })
    logger.info("Mapeo: Módulo 'sharepoint_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'sharepoint_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'sharepoint_actions': {e}")

# Teams (Chats, Equipos, Canales)
try:
    from .actions import teams_actions as teams
    available_actions.update({
        "teams_list_chats": teams.listar_chats,
        "teams_get_chat": teams.obtener_chat,
        "teams_create_chat": teams.crear_chat,
        "teams_send_chat_message": teams.enviar_mensaje_chat,
        "teams_get_chat_messages": teams.obtener_mensajes_chat,
        "teams_update_chat_message": teams.actualizar_mensaje_chat,
        "teams_delete_chat_message": teams.eliminar_mensaje_chat,
        "teams_list_joined_teams": teams.listar_equipos,
        "teams_get_team_details": teams.obtener_equipo,
        "teams_create_team": teams.crear_equipo,
        "teams_archive_team": teams.archivar_equipo,
        "teams_unarchive_team": teams.unarchivar_equipo,
        "teams_delete_team": teams.eliminar_equipo,
        "teams_list_channels": teams.listar_canales,
        "teams_get_channel": teams.obtener_canal,
        "teams_create_channel": teams.crear_canal,
        "teams_update_channel": teams.actualizar_canal,
        "teams_delete_channel": teams.eliminar_canal,
        "teams_send_channel_message": teams.enviar_mensaje_canal,
    })
    logger.info("Mapeo: Módulo 'teams_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'teams_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'teams_actions': {e}")

# Office (Excel vía Graph)
try:
    from .actions import office_actions as office
    available_actions.update({
        "excel_create_workbook": office.crear_libro_excel,
        "excel_read_cell": office.leer_celda_excel,
        "excel_write_cell": office.escribir_celda_excel,
        "excel_create_table": office.crear_tabla_excel,
        "excel_add_table_rows": office.agregar_filas_tabla_excel,
        "word_create_document": office.crear_documento_word,
        "word_replace_content": office.reemplazar_contenido_word,
        # "word_get_content": office.obtener_documento_word_binario, # Devuelve bytes
    })
    logger.info("Mapeo: Módulo 'office_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'office_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'office_actions': {e}")

# Planner & ToDo
try:
    from .actions import planner_todo_actions as pt
    available_actions.update({
        "planner_list_plans": pt.listar_planes,
        "planner_get_plan": pt.obtener_plan,
        "planner_create_plan": pt.crear_plan,
        "planner_update_plan": pt.actualizar_plan,
        "planner_delete_plan": pt.eliminar_plan,
        "planner_list_tasks": pt.listar_tareas_planner,
        "planner_create_task": pt.crear_tarea_planner,
        "planner_update_task": pt.actualizar_tarea_planner,
        "planner_delete_task": pt.eliminar_tarea_planner,
        "todo_list_lists": pt.listar_listas_todo,
        "todo_create_list": pt.crear_lista_todo,
        "todo_update_list": pt.actualizar_lista_todo,
        "todo_delete_list": pt.eliminar_lista_todo,
        "todo_list_tasks": pt.listar_tareas_todo,
        "todo_create_task": pt.crear_tarea_todo,
        "todo_update_task": pt.actualizar_tarea_todo,
        "todo_delete_task": pt.eliminar_tarea_todo,
        "todo_complete_task": pt.completar_tarea_todo,
    })
    logger.info("Mapeo: Módulo 'planner_todo_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'planner_todo_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'planner_todo_actions': {e}")

# Power Automate
try:
    from .actions import power_automate_actions as pa
    available_actions.update({
        "flow_list": pa.listar_flows,
        "flow_get": pa.obtener_flow,
        # "flow_create": pa.crear_flow, # Implementado pero requiere definicion compleja
        # "flow_update": pa.actualizar_flow, # Implementado pero requiere definicion compleja
        "flow_delete": pa.eliminar_flow,
        "flow_run_trigger": pa.ejecutar_flow,
        "flow_get_run_status": pa.obtener_estado_ejecucion_flow,
    })
    logger.info("Mapeo: Módulo 'power_automate_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'power_automate_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'power_automate_actions': {e}")

# Power BI
try:
    from .actions import power_bi_actions as pbi
    available_actions.update({
        "pbi_list_workspaces": pbi.listar_workspaces,
        "pbi_list_datasets": pbi.listar_datasets,
        "pbi_refresh_dataset": pbi.refrescar_dataset,
        "pbi_get_refresh_status": pbi.obtener_estado_refresco_dataset,
        "pbi_list_reports": pbi.listar_reports,
    })
    logger.info("Mapeo: Módulo 'power_bi_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'power_bi_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'power_bi_actions': {e}")

# OpenAI (Azure OpenAI via AAD)
try:
    from .actions import openai_actions as ai
    available_actions.update({
        # Asegúrate que los nombres de función coincidan con openai_actions.py
        "openai_chat_completion": ai.openai_chat_completion,
        "openai_get_embeddings": ai.openai_get_embeddings,
        # Añadir mapeos para imagen/transcripción aquí cuando se implementen
    })
    logger.info("Mapeo: Módulo 'openai_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'openai_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'openai_actions': {e}")

# Microsoft Forms (Solo listar)
try:
    from .actions import forms_actions as forms
    available_actions.update({
        "forms_list_files": forms.listar_formularios_en_drive,
        "forms_get_responses_info": forms.obtener_respuestas_formulario, # Devuelve error informativo
    })
    logger.info("Mapeo: Módulo 'forms_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'forms_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'forms_actions': {e}")

# Microsoft Stream (on SharePoint)
try:
    from .actions import stream_actions as stream
    available_actions.update({
        "stream_list_videos": stream.listar_videos,
        "stream_get_video_metadata": stream.obtener_metadatos_video,
        "stream_get_transcription_info": stream.obtener_transcripcion_video, # Devuelve error informativo
    })
    logger.info("Mapeo: Módulo 'stream_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'stream_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'stream_actions': {e}")

# Microsoft Bookings
try:
    from .actions import bookings_actions as bookings
    available_actions.update({
        "bookings_list_businesses": bookings.listar_negocios_bookings,
        "bookings_get_business": bookings.obtener_negocio_bookings,
        "bookings_list_services": bookings.listar_servicios_bookings,
        "bookings_list_appointments": bookings.listar_citas_bookings,
        "bookings_create_appointment": bookings.crear_cita_bookings,
        "bookings_cancel_appointment": bookings.cancelar_cita_bookings,
    })
    logger.info("Mapeo: Módulo 'bookings_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'bookings_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'bookings_actions': {e}")

# Viva Insights
try:
    from .actions import viva_insights_actions as viva
    available_actions.update({
        "viva_get_activity_stats": viva.obtener_estadisticas_actividad,
    })
    logger.info("Mapeo: Módulo 'viva_insights_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'viva_insights_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'viva_insights_actions': {e}")

# GitHub
try:
    from .actions import github_actions as gh
    available_actions.update({
        "github_list_user_repos": gh.listar_repositorios_usuario,
        "github_create_issue": gh.crear_issue,
        "github_list_repo_issues": gh.listar_issues,
    })
    logger.info("Mapeo: Módulo 'github_actions' cargado y mapeado.")
except ImportError as e: logger.warning(f"Mapeo: No se pudo importar 'github_actions': {e}")
except AttributeError as e: logger.warning(f"Mapeo: Falta función en 'github_actions': {e}")


# --- Verificación Final ---
final_actions_count = len(available_actions)
logger.info(f"--- MAPEO FINALIZADO ---")
logger.info(f"Total acciones cargadas y mapeadas: {final_actions_count}")
# Loguear las claves mapeadas puede ser útil para depuración
logger.debug(f"Acciones mapeadas final: {sorted(list(available_actions.keys()))}") 

if final_actions_count == 0:
    logger.critical("¡¡¡MAPEO CRÍTICO!!! No se cargó NINGUNA acción. "
                    "El sistema no podrá ejecutar ninguna tarea. "
                    "Revise todos los logs de importación anteriores de los módulos de acción.")

# --- FIN DEL MÓDULO mapping_actions.py ---