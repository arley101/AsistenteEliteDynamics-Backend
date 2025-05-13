import os
import ast
import re
from collections import defaultdict

# --- Configuración ---
BASE_PATH = "MyHttpTrigger" # Ruta a la carpeta de tu Azure Function
ACTIONS_SUBDIR = "actions" # Subcarpeta para los módulos de acciones
MAPPING_FILE_PATH = os.path.join(BASE_PATH, "mapping_actions.py")
ACTIONS_DIR_PATH = os.path.join(BASE_PATH, ACTIONS_SUBDIR)

# Plantilla para el contenido de un nuevo archivo de acción
NEW_FILE_TEMPLATE = """# -*- coding: utf-8 -*-
# MyHttpTrigger/actions/{module_filename}
import logging
from typing import Dict, List, Optional, Any, Union # Añadir más tipos según necesidad

# Importar el cliente autenticado y las constantes
from ..shared.helpers.http_client import AuthenticatedHttpClient
from ..shared import constants

logger = logging.getLogger(__name__)

# --- Placeholder Functions ---
"""

# Plantilla para una función placeholder
FUNCTION_TEMPLATE = """
def {function_name}(client: AuthenticatedHttpClient, params: Dict[str, Any]) -> Dict[str, Any]:
    \"\"\"
    Placeholder para la acción: {function_name}
    Servicio: {service_name}
    \"\"\"
    action_name_log = "{function_name}" 
    logger.warning(f"Acción '{{action_name_log}}' del servicio '{{__name__}}' no implementada todavía.")
    return {{
        "status": "not_implemented",
        "message": f"Acción '{{action_name_log}}' no implementada todavía.",
        "service_module": __name__,
        "http_status": 501
    }}
"""

def get_action_map_from_file(filepath):
    """
    Extrae el ACTION_MAP de mapping_actions.py usando AST.
    Devuelve un diccionario: {'module_name_in_map': ['function_name1', 'function_name2']}
    """
    modules_and_functions = defaultdict(list)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        action_map_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'ACTION_MAP':
                        action_map_node = node.value
                        break
                if action_map_node:
                    break
        
        if action_map_node and isinstance(action_map_node, ast.Dict):
            for key_node, value_node in zip(action_map_node.keys, action_map_node.values):
                if isinstance(key_node, (ast.Constant, ast.Str)) and isinstance(value_node, ast.Attribute):
                    # action_key = key_node.s if isinstance(key_node, ast.Str) else key_node.value
                    
                    # value_node.value es el objeto antes del '.' (ej. calendario_actions)
                    # value_node.attr es el atributo después del '.' (ej. calendar_list_events)
                    if isinstance(value_node.value, ast.Name):
                        module_name_in_map = value_node.value.id 
                        function_name = value_node.attr
                        modules_and_functions[module_name_in_map].append(function_name)
        
        return modules_and_functions
    except FileNotFoundError:
        print(f"ERROR: No se encontró el archivo de mapeo: {filepath}")
        return None
    except Exception as e:
        print(f"ERROR: No se pudo parsear {filepath}: {e}")
        return None

def ensure_directory_exists(path):
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"Directorio creado: {path}")

def main():
    print("Iniciando script para generar/verificar placeholders de acciones...")
    
    parsed_action_map = get_action_map_from_file(MAPPING_FILE_PATH)
    if not parsed_action_map:
        print("No se pudo procesar ACTION_MAP. Saliendo.")
        return

    ensure_directory_exists(ACTIONS_DIR_PATH)
    
    print(f"\nProcesando módulos definidos en {MAPPING_FILE_PATH}:")
    
    for module_name_in_map, function_names in parsed_action_map.items():
        # module_name_in_map es como 'calendario_actions', 'sharepoint_actions'
        # El nombre de archivo será {module_name_in_map}.py
        module_filename = f"{module_name_in_map}.py"
        module_filepath = os.path.join(ACTIONS_DIR_PATH, module_filename)
        
        service_name_guess = module_name_in_map.replace("_actions", "") # Para el comentario en la función

        if not os.path.exists(module_filepath):
            print(f"  Archivo NO encontrado: {module_filepath}. Creando con placeholders...")
            with open(module_filepath, 'w', encoding='utf-8') as f:
                f.write(NEW_FILE_TEMPLATE.format(module_filename=module_filename))
                for func_name in sorted(list(set(function_names))): # Evitar duplicados si los hubiera
                    f.write(FUNCTION_TEMPLATE.format(function_name=func_name, service_name=service_name_guess))
            print(f"    -> Creado: {module_filepath} con {len(function_names)} placeholder(s).")
        else:
            print(f"  Archivo YA EXISTE: {module_filepath}. Verificando funciones faltantes...")
            try:
                with open(module_filepath, 'r', encoding='utf-8') as f:
                    existing_content = f.read()
                
                missing_functions_in_file = []
                for func_name in sorted(list(set(function_names))):
                    # Búsqueda simple de la definición de función
                    if not re.search(rf"def\s+{func_name}\s*\(", existing_content):
                        missing_functions_in_file.append(func_name)
                
                if missing_functions_in_file:
                    print(f"    ¡ATENCIÓN! Funciones mapeadas en ACTION_MAP pero NO encontradas en '{module_filename}':")
                    for func_name in missing_functions_in_file:
                        print(f"      - {func_name}")
                    print(f"      Considera añadir placeholders para estas funciones en '{module_filename}'.")
                    # Opcional: Aquí se podría añadir código para APILAR los placeholders faltantes
                    # con cuidado de no duplicar imports o logger. Por seguridad, lo dejamos manual.
                else:
                    print(f"    Todas las {len(function_names)} funciones mapeadas para '{module_name_in_map}' parecen estar definidas en el archivo.")
            except Exception as e:
                print(f"    ERROR: No se pudo leer o analizar el archivo existente {module_filepath}: {e}")
                
    print("\nProceso completado.")
    print("RECUERDA: Revisa los archivos creados/modificados y completa la lógica de las acciones prioritarias.")

if __name__ == "__main__":
    main()