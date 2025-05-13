# -*- coding: utf-8 -*-
import logging
from ..shared import constants
from ..shared.helpers.http_client import AuthenticatedHttpClient

logger = logging.getLogger(__name__)

# --- Placeholder Functions ---

def list_resource_groups(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "azure_list_resource_groups"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def list_resources_in_rg(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "azure_list_resources_in_rg"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def get_resource(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "azure_get_resource"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def create_deployment(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "azure_create_deployment"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def list_functions(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "azure_list_functions"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def get_function_status(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "azure_get_function_status"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def restart_function_app(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "azure_restart_function_app"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def list_logic_apps(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "azure_list_logic_apps"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def trigger_logic_app(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "azure_trigger_logic_app"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def get_logic_app_run_history(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "azure_get_logic_app_run_history"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

# ... (añadir más placeholders según sea necesario para Azure Mgmt)