# -*- coding: utf-8 -*-
"""
Mapeo central de todas las acciones soportadas por el asistente.
Cada clave representa el string 'action' esperado en la solicitud JSON,
y el valor es la referencia a la función Python que debe ejecutarla.
"""

import logging

# Importar todos los módulos de acciones desde la carpeta 'actions'
# Usamos '.' porque 'actions' es un subdirectorio de 'MyHttpTrigger' donde está este archivo.
from .actions import (
    azuremgmt_actions,
    bookings_actions,
    calendario_actions,
    correo_actions,
    # forge_actions, # Descomentar cuando se creen (requieren auth externa)
    forms_actions,
    # github_actions, # Descomentar cuando se creen (requieren auth externa)
    graph_actions,
    # office_actions, # Descomentar cuando se creen (requieren enfoque especial)
    onedrive_actions,
    openai_actions,
    planner_actions,
    powerbi_actions,
    sharepoint_actions,
    stream_actions,
    teams_actions,
    todo_actions,
    userprofile_actions,
    users_actions,
    vivainsights_actions
)

logger = logging.getLogger(__name__)

# --- El Gran Mapa de Acciones ---
# Clave: string 'action' recibido en la solicitud
# Valor: referencia a la función Python a ejecutar
ACTION_MAP = {

    # --- Azure Management Actions ---
    "azure_list_resource_groups": azuremgmt_actions.list_resource_groups,
    "azure_list_resources_in_rg": azuremgmt_actions.list_resources_in_rg,
    "azure_get_resource": azuremgmt_actions.get_resource,
    "azure_create_deployment": azuremgmt_actions.create_deployment,
    "azure_list_functions": azuremgmt_actions.list_functions,
    "azure_get_function_status": azuremgmt_actions.get_function_status,
    "azure_restart_function_app": azuremgmt_actions.restart_function_app,
    "azure_list_logic_apps": azuremgmt_actions.list_logic_apps,
    "azure_trigger_logic_app": azuremgmt_actions.trigger_logic_app,
    "azure_get_logic_app_run_history": azuremgmt_actions.get_logic_app_run_history,
    # ... (más acciones de Azure Management)

    # --- Bookings Actions ---
    "bookings_list_businesses": bookings_actions.list_businesses,
    "bookings_get_business": bookings_actions.get_business,
    "bookings_list_services": bookings_actions.list_services,
    "bookings_list_staff": bookings_actions.list_staff,
    "bookings_create_appointment": bookings_actions.create_appointment,
    "bookings_get_appointment": bookings_actions.get_appointment,
    "bookings_cancel_appointment": bookings_actions.cancel_appointment,
    "bookings_list_appointments": bookings_actions.list_appointments,
    # ... (más acciones de Bookings)

    # --- Calendario Actions ---
    "calendar_list_events": calendario_actions.calendar_list_events,
    "calendar_create_event": calendario_actions.calendar_create_event,
    "calendar_get_event": calendario_actions.get_event,
    "calendar_update_event": calendario_actions.update_event,
    "calendar_delete_event": calendario_actions.delete_event,
    "calendar_find_meeting_times": calendario_actions.find_meeting_times,
    "calendar_get_schedule": calendario_actions.get_schedule,
    # ... (más acciones de Calendario)

    # --- Correo Actions ---
    "email_list_messages": correo_actions.list_messages,
    "email_get_message": correo_actions.get_message,
    "email_send_message": correo_actions.send_message,
    "email_reply_message": correo_actions.reply_message,
    "email_forward_message": correo_actions.forward_message,
    "email_delete_message": correo_actions.delete_message,
    "email_move_message": correo_actions.move_message,
    "email_list_folders": correo_actions.list_folders,
    "email_create_folder": correo_actions.create_folder,
    "email_search_messages": correo_actions.search_messages,
    # ... (más acciones de Correo)

    # --- Forge Actions (Requiere Auth Externa) ---
    # "forge_upload_model": forge_actions.upload_model,
    # "forge_translate_model": forge_actions.translate_model,
    # "forge_get_manifest": forge_actions.get_manifest,
    # "forge_get_thumbnail": forge_actions.get_thumbnail,
    # ... (más acciones de Forge)

    # --- Forms Actions ---
    "forms_list_forms": forms_actions.list_forms,
    "forms_get_form": forms_actions.get_form,
    "forms_get_form_responses": forms_actions.get_form_responses,
    # ... (más acciones de Forms)

    # --- GitHub Actions (Requiere Auth Externa) ---
    # "github_list_repos": github_actions.list_repositories,
    # "github_get_repo": github_actions.get_repo,
    # "github_get_repo_content": github_actions.get_repo_content,
    # "github_create_repo": github_actions.create_repo,
    # "github_list_issues": github_actions.list_issues,
    # "github_get_issue": github_actions.get_issue,
    # "github_create_issue": github_actions.create_issue,
    # "github_update_issue": github_actions.update_issue,
    # "github_add_comment_issue": github_actions.add_comment_issue,
    # "github_list_prs": github_actions.list_prs,
    # "github_get_pr": github_actions.get_pr,
    # "github_create_pr": github_actions.create_pr,
    # "github_merge_pr": github_actions.merge_pr,
    # "github_list_workflows": github_actions.list_workflows,
    # "github_trigger_workflow": github_actions.trigger_workflow,
    # "github_get_workflow_run": github_actions.get_workflow_run,
    # ... (más acciones de GitHub)

    # --- Graph Actions (Generales o no clasificadas) ---
    "graph_generic_get": graph_actions.generic_get,
    "graph_generic_post": graph_actions.generic_post,
    # ... (acciones genéricas si es necesario)

    # --- Office Actions (Enfoque especial, pueden ser placeholders largos) ---
    # "office_run_excel_script": office_actions.run_excel_script,
    # "office_update_word_document": office_actions.update_word_document,
    # ... (más acciones de Office)

    # --- OneDrive Actions ---
    "onedrive_list_items": onedrive_actions.list_items,
    "onedrive_get_item": onedrive_actions.get_item,
    "onedrive_upload_file": onedrive_actions.upload_file,
    "onedrive_download_file": onedrive_actions.download_file,
    "onedrive_delete_item": onedrive_actions.delete_item,
    "onedrive_create_folder": onedrive_actions.create_folder,
    "onedrive_move_item": onedrive_actions.move_item,
    "onedrive_copy_item": onedrive_actions.copy_item,
    "onedrive_search_items": onedrive_actions.search_items,
    "onedrive_get_sharing_link": onedrive_actions.get_sharing_link,
    # ... (más acciones de OneDrive)

    # --- Azure OpenAI Actions ---
    "openai_chat_completion": openai_actions.chat_completion,
    "openai_completion": openai_actions.completion,
    "openai_get_embedding": openai_actions.get_embedding,
    "openai_list_models": openai_actions.list_models,
    # ... (más acciones de OpenAI)

    # --- Planner Actions ---
    "planner_list_plans": planner_actions.list_plans,
    "planner_get_plan": planner_actions.get_plan,
    "planner_list_tasks": planner_actions.list_tasks,
    "planner_create_task": planner_actions.create_task,
    "planner_get_task": planner_actions.get_task,
    "planner_update_task": planner_actions.update_task,
    "planner_delete_task": planner_actions.delete_task,
    "planner_list_buckets": planner_actions.list_buckets,
    "planner_create_bucket": planner_actions.create_bucket,
    # ... (más acciones de Planner)

    # --- Power BI Actions ---
    "powerbi_list_reports": powerbi_actions.list_reports,
    "powerbi_export_report": powerbi_actions.export_report,
    "powerbi_list_dashboards": powerbi_actions.list_dashboards,
    "powerbi_list_datasets": powerbi_actions.list_datasets,
    "powerbi_refresh_dataset": powerbi_actions.refresh_dataset,
    # ... (más acciones de Power BI)

    # --- SharePoint Actions ---
    "sp_list_lists": sharepoint_actions.list_lists,
    "sp_get_list": sharepoint_actions.get_list,
    "sp_create_list": sharepoint_actions.create_list,
    "sp_update_list": sharepoint_actions.update_list,
    "sp_delete_list": sharepoint_actions.delete_list,
    "sp_list_list_items": sharepoint_actions.list_list_items,
    "sp_get_list_item": sharepoint_actions.get_list_item,
    "sp_add_list_item": sharepoint_actions.add_list_item,
    "sp_update_list_item": sharepoint_actions.update_list_item,
    "sp_delete_list_item": sharepoint_actions.delete_list_item,
    "sp_search_list_items": sharepoint_actions.search_list_items,
    "sp_list_document_libraries": sharepoint_actions.list_document_libraries,
    "sp_list_folder_contents": sharepoint_actions.list_folder_contents,
    "sp_get_file_metadata": sharepoint_actions.get_file_metadata,
    "sp_upload_document": sharepoint_actions.upload_document,
    "sp_download_document": sharepoint_actions.download_document,
    "sp_delete_document": sharepoint_actions.delete_document,
    "sp_create_folder": sharepoint_actions.create_folder,
    "sp_move_item": sharepoint_actions.move_item,
    "sp_copy_item": sharepoint_actions.copy_item,
    "sp_update_file_metadata": sharepoint_actions.update_file_metadata,
    "sp_get_site_info": sharepoint_actions.get_site_info,
    "sp_search_sites": sharepoint_actions.search_sites,
    "sp_memory_ensure_list": sharepoint_actions.memory_ensure_list,
    "sp_memory_save": sharepoint_actions.memory_save,
    "sp_memory_get": sharepoint_actions.memory_get,
    "sp_memory_delete": sharepoint_actions.memory_delete,
    "sp_memory_list_keys": sharepoint_actions.memory_list_keys,
    "sp_memory_export_session": sharepoint_actions.memory_export_session,
    "sp_get_sharing_link": sharepoint_actions.get_sharing_link,
    "sp_add_item_permissions": sharepoint_actions.add_item_permissions,
    "sp_remove_item_permissions": sharepoint_actions.remove_item_permissions,
    "sp_list_item_permissions": sharepoint_actions.list_item_permissions,
    # ... (más acciones de SharePoint)

    # --- Stream Actions (basado en API moderna sobre SP/OD) ---
    "stream_get_video_playback_url": stream_actions.get_video_playback_url,
    # ... (otras acciones específicas de Stream si existen/son necesarias)

    # --- Teams Actions ---
    "teams_list_joined_teams": teams_actions.list_joined_teams,
    "teams_get_team": teams_actions.get_team,
    "teams_list_channels": teams_actions.list_channels,
    "teams_get_channel": teams_actions.get_channel,
    "teams_send_channel_message": teams_actions.send_channel_message,
    "teams_list_channel_messages": teams_actions.list_channel_messages,
    "teams_reply_to_message": teams_actions.reply_to_message,
    "teams_send_chat_message": teams_actions.send_chat_message,
    "teams_list_chats": teams_actions.list_chats,
    "teams_get_chat": teams_actions.get_chat,
    "teams_create_chat": teams_actions.create_chat,
    "teams_list_chat_messages": teams_actions.list_chat_messages,
    "teams_schedule_meeting": teams_actions.schedule_meeting,
    "teams_get_meeting_details": teams_actions.get_meeting_details,
    "teams_list_members": teams_actions.list_members,
    # ... (más acciones de Teams)

    # --- To Do Actions ---
    "todo_list_task_lists": todo_actions.list_task_lists,
    "todo_create_task_list": todo_actions.create_task_list,
    "todo_list_tasks": todo_actions.list_tasks,
    "todo_create_task": todo_actions.create_task,
    "todo_get_task": todo_actions.get_task,
    "todo_update_task": todo_actions.update_task,
    "todo_delete_task": todo_actions.delete_task,
    # ... (más acciones de To Do)

    # --- User Profile Actions ---
    "profile_get_my_profile": userprofile_actions.get_my_profile,
    "profile_get_my_manager": userprofile_actions.get_my_manager,
    "profile_get_my_direct_reports": userprofile_actions.get_my_direct_reports,
    "profile_get_my_photo": userprofile_actions.get_my_photo,
    "profile_update_my_profile": userprofile_actions.update_my_profile,
    # ... (más acciones de User Profile)

    # --- Users Actions (Directory) ---
    "user_list_users": users_actions.list_users,
    "user_get_user": users_actions.get_user,
    "user_create_user": users_actions.create_user,
    "user_update_user": users_actions.update_user,
    "user_delete_user": users_actions.delete_user,
    "user_list_groups": users_actions.list_groups,
    "user_get_group": users_actions.get_group,
    "user_list_group_members": users_actions.list_group_members,
    "user_add_group_member": users_actions.add_group_member,
    "user_remove_group_member": users_actions.remove_group_member,
    "user_check_group_membership": users_actions.check_group_membership,
    # ... (más acciones de Users/Directory)

    # --- Viva Insights Actions ---
    "viva_get_my_analytics": vivainsights_actions.get_my_analytics,
    "viva_get_focus_plan": vivainsights_actions.get_focus_plan,
    # ... (más acciones de Viva Insights)

}

# Log de confirmación al cargar el módulo
logger.info(f"ACTION_MAP cargado. Número total de acciones definidas: {len(ACTION_MAP)}")

# Opcional: Validación para asegurar que todas las funciones mapeadas existen
# (Esto fallaría ahora porque son placeholders, pero útil más adelante)
# for action_name, function_ref in ACTION_MAP.items():
#     if not callable(function_ref):
#         logger.error(f"Error en ACTION_MAP: '{action_name}' no apunta a una función válida ({function_ref}).")
#         # Podrías lanzar un error aquí si quieres ser estricto