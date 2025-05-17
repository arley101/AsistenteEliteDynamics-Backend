# -*- coding: utf-8 -*-
import logging
from shared import constants
from shared.helpers.http_client import AuthenticatedHttpClient

logger = logging.getLogger(__name__)

# --- Placeholder Functions ---

def list_businesses(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "bookings_list_businesses"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def get_business(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "bookings_get_business"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def list_services(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "bookings_list_services"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def list_staff(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "bookings_list_staff"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def create_appointment(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "bookings_create_appointment"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def get_appointment(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "bookings_get_appointment"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def cancel_appointment(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "bookings_cancel_appointment"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

def list_appointments(client: AuthenticatedHttpClient, params: dict) -> dict:
    action_name = "bookings_list_appointments"
    logger.warning(f"Action '{action_name}' not implemented yet.")
    return {"error": "NotImplemented", "message": f"Action '{action_name}' not implemented yet.", "status_code": 501}

# ... (añadir más placeholders según sea necesario para Bookings)