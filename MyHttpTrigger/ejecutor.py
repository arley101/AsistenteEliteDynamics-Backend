# MyHttpTrigger/ejecutor.py
import logging
from typing import Dict, Any, Callable # Callable es para el tipo de las funciones de acción

# Intentar importar APP_NAME para el logger, con un fallback
try:
    from .shared.constants import APP_NAME
except ImportError:
    # Este fallback es útil si ejecutas este módulo de forma aislada para pruebas unitarias
    # o si el linter local tiene problemas con la importación relativa antes de que todo esté en su sitio.
    APP_NAME = "EliteDynamicsPro"
    logging.warning("ejecutor.py: Usando APP_NAME de fallback para el logger.")

logger = logging.getLogger(f"{APP_NAME}.ejecutor")

def execute_action(
    action_name: str,
    parametros: Dict[str, Any],
    headers: Dict[str, str], # Contiene el token de autorización y otras cabeceras necesarias
    available_actions: Dict[str, Callable] # El diccionario que mapea nombres a funciones
) -> Dict[str, Any]:
    """
    Busca y ejecuta la función de acción correspondiente al action_name.
    Las funciones de acción deben tener la firma: func(parametros: Dict, headers: Dict) -> Dict.

    Args:
        action_name (str): El nombre de la acción solicitada (ej. "email_list").
        parametros (Dict[str, Any]): Parámetros específicos para la acción,
                                     extraídos del cuerpo JSON de la solicitud.
        headers (Dict[str, str]): Cabeceras HTTP que incluyen el token de autorización
                                  (ej. {'Authorization': 'Bearer <token_obo_o_app>'}).
                                  Se pasan a la función de acción.
        available_actions (Dict[str, Callable]): El diccionario (de mapping_actions.py)
                                                 que mapea los nombres de acción a las
                                                 funciones Python correspondientes.

    Returns:
        Dict[str, Any]: El resultado de la función de acción, que se espera sea un
                        diccionario (idealmente con "status": "success"/"error").
    """
    logger.info(f"Ejecutor: Intentando ejecutar la acción '{action_name}'...")
    logger.debug(f"Ejecutor: Parámetros recibidos para la acción: {parametros}")
    # No loguear 'headers' por defecto para no exponer tokens, a menos que sea en nivel TRACE/DEBUG muy bajo.
    # logger.debug(f"Ejecutor: Cabeceras recibidas: {headers}")
    logger.debug(f"Ejecutor: Acciones disponibles en el mapeo: {list(available_actions.keys())}")

    action_function = available_actions.get(action_name)

    # 1. Verificar si la acción solicitada existe en nuestro mapeo
    if not action_function:
        logger.error(f"Ejecutor: Acción '{action_name}' no encontrada en 'available_actions'.")
        return {"status": "error", "message": f"Acción no implementada o nombre incorrecto: '{action_name}'. Verifique las acciones disponibles."}

    # 2. Verificar si lo que obtuvimos del mapeo es realmente una función que podemos llamar
    if not callable(action_function):
        logger.error(f"Ejecutor: La acción '{action_name}' está mapeada a un objeto que no es una función (tipo: {type(action_function)}). Revise 'mapping_actions.py'.")
        return {"status": "error", "message": f"Error de configuración interna: La acción '{action_name}' no está correctamente configurada para ser ejecutada."}

    # 3. Ejecutar la función de acción
    try:
        logger.info(f"Ejecutor: Llamando a la función para la acción '{action_name}'...")
        # Las funciones de acción ahora esperan 'parametros' y 'headers' directamente
        result = action_function(parametros=parametros, headers=headers)
        
        logger.info(f"Ejecutor: Acción '{action_name}' completada por la función.")

        # 4. Validar y estandarizar la respuesta de la acción
        if not isinstance(result, dict):
            logger.warning(f"La acción '{action_name}' devolvió un tipo no esperado ({type(result)}). Se recomienda que las acciones devuelvan un diccionario. Envolviendo el resultado.")
            # Devolver un diccionario estándar incluso si la acción no lo hizo
            return {"status": "success_unstructured_response", "data": result, "message": f"Acción '{action_name}' completada, pero la respuesta no fue un diccionario estructurado."}
        
        if "status" not in result:
            logger.warning(f"La acción '{action_name}' devolvió un diccionario sin una clave 'status'. Asumiendo 'success' por defecto, pero se recomienda que la acción lo incluya explícitamente.")
            result["status"] = "success" # Forzar un status si no viene

        return result

    except TypeError as te:
        # Este error es común si la función de acción no fue definida para aceptar (parametros, headers)
        # o si los parámetros enviados no son los que espera la función específica (ej. faltan requeridos).
        logger.error(f"Ejecutor: TypeError al llamar a la acción '{action_name}'. ¿La firma de la función es correcta? ¿Se enviaron los parámetros correctos? Detalles: {te}", exc_info=True)
        return {"status": "error", "message": f"Error en los parámetros o la firma de la acción '{action_name}'. Detalles técnicos: {str(te)}"}
    except Exception as e:
        # Captura cualquier otra excepción inesperada que ocurra DENTRO de la ejecución de la acción.
        logger.error(f"Ejecutor: Excepción inesperada durante la ejecución de la acción '{action_name}': {type(e).__name__} - {e}", exc_info=True)
        # No exponer detalles internos sensibles de la excepción al cliente final
        return {"status": "error", "message": f"Error interno inesperado al procesar la acción '{action_name}'."}