# EliteDynamicsPro_Local/ejecutor.py
import logging
# Importaciones directas desde la raíz o paquetes hermanos
from shared import constants
from shared.helpers import http_client 
import mapping_actions 

logger = logging.getLogger(__name__)
logger.info(f"Módulo '{__name__}' (en la raíz del proyecto) cargado.")
# La lógica de despacho está en MyHttpTrigger/__init__.py, 
# este archivo es importado por él.