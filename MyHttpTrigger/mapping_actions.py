# MyHttpTrigger/mapping_actions.py (VERSIÓN SIMPLIFICADA PARA PRUEBA)
import logging

# Importamos ÚNICAMENTE la acción de prueba para Graph
try:
    from .actions.graph_test_actions import obtener_perfil_identidad_administrada
    graph_test_action_imported_successfully = True
    logging.getLogger("EliteDynamicsPro.MappingActions").info("Acción 'obtener_perfil_identidad_administrada' importada correctamente.")
except ImportError as e:
    logging.getLogger("EliteDynamicsPro.MappingActions").error(f"FALLO AL IMPORTAR 'obtener_perfil_identidad_administrada' desde .actions.graph_test_actions: {e}. La acción de prueba no estará disponible.")
    graph_test_action_imported_successfully = False
    # Definimos una función dummy para que el mapeo no falle si se intenta llamar
    def obtener_perfil_identidad_administrada(params, headers):
        return {"status": "error_action_not_loaded", "message": "La función de acción 'obtener_perfil_identidad_administrada' no pudo ser importada."}

# Mapeamos SOLAMENTE la acción de prueba
available_actions = {}
if graph_test_action_imported_successfully:
    available_actions["obtener_perfil_app_test"] = obtener_perfil_identidad_administrada

# Logging y verificación
map_logger = logging.getLogger("EliteDynamicsPro.MappingActions") # Usa un nombre consistente

if not available_actions:
    map_logger.warning("MAPEADOR DE ACCIONES (SIMPLIFICADO): El diccionario 'available_actions' está VACÍO o la acción de prueba no se pudo cargar. Ninguna acción será funcional.")
else:
    map_logger.info(f"MAPEADOR DE ACCIONES (SIMPLIFICADO): Cargado. Acciones disponibles: {list(available_actions.keys())}")
    for action_name, func_ref in available_actions.items():
        if not callable(func_ref):
            map_logger.error(f"MAPEADOR DE ACCIONES (SIMPLIFICADO) - ERROR: La acción mapeada '{action_name}' NO es una función llamable.")