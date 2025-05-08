# MyHttpTrigger/actions/github_actions.py
import logging
import requests # Usaremos requests directamente para la API de GitHub
import json
import os
from typing import Dict, List, Optional, Any

# Importar constantes solo para logging y timeout base
try:
    from ..shared.constants import APP_NAME, DEFAULT_API_TIMEOUT
except ImportError as e:
    logging.warning(f"No se pudo importar constantes compartidas en GitHub: {e}. Usando fallbacks.")
    APP_NAME = "EliteDynamicsPro" # Fallback
    DEFAULT_API_TIMEOUT = 60 # Fallback timeout para GitHub

logger = logging.getLogger(f"{APP_NAME}.actions.github")

# --- Constantes y Configuración Específica para GitHub API ---
GITHUB_API_BASE_URL = "https://api.github.com"
# Leer PAT de variable de entorno (¡DEBE estar en local.settings.json / App Settings!)
GITHUB_PAT = os.environ.get("GITHUB_PAT")

# --- Helper de Autenticación (Específico para GitHub PAT) ---
def _get_github_auth_headers() -> Dict[str, str]:
    """Construye las cabeceras de autenticación para GitHub API usando PAT."""
    if not GITHUB_PAT:
        msg = "Variable de entorno 'GITHUB_PAT' no configurada. No se puede autenticar con GitHub API."
        logger.critical(msg)
        raise ValueError(msg) # Lanzar error si falta el PAT

    # GitHub recomienda 'Accept' y usa 'Bearer' o 'token' para PAT
    headers = {
        'Authorization': f'Bearer {GITHUB_PAT}',
        'Accept': 'application/vnd.github.v3+json', # Versión recomendada de la API
        'X-GitHub-Api-Version': '2022-11-28' # Especificar versión API
    }
    return headers

# ---- FUNCIONES DE ACCIÓN PARA GITHUB ----
# Nota: El parámetro 'headers' de la firma (con token OBO) SE IGNORA aquí.
# Usamos _get_github_auth_headers() en su lugar.

def listar_repositorios_usuario(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Lista los repositorios del usuario autenticado (asociado al PAT).

    Args:
        parametros (Dict[str, Any]): Opcional:
            'visibility' (str): 'all', 'public', 'private'. Default 'all'.
            'affiliation' (str): 'owner,collaborator,organization_member'. Default 'owner,collaborator'.
            'sort' (str): 'created', 'updated', 'pushed', 'full_name'. Default 'pushed'.
            'direction' (str): 'asc' o 'desc'. Default 'desc'.
            'per_page' (int): Resultados por página. Default 30, max 100.
            'page' (int): Número de página a obtener. Default 1.
        headers (Dict[str, str]): Ignorado. Se usa GITHUB_PAT.

    Returns:
        Dict[str, Any]: {"status": "success", "data": [lista_repos]} o error.
    """
    visibility: str = parametros.get('visibility', 'all')
    affiliation: str = parametros.get('affiliation', 'owner,collaborator')
    sort: str = parametros.get('sort', 'pushed')
    direction: str = parametros.get('direction', 'desc')
    per_page: int = min(int(parametros.get('per_page', 30)), 100)
    page: int = int(parametros.get('page', 1))

    try:
        github_headers = _get_github_auth_headers()
    except ValueError as auth_err:
        return {"status": "error", "message": str(auth_err)}

    url = f"{GITHUB_API_BASE_URL}/user/repos"
    params_query = {
        "visibility": visibility,
        "affiliation": affiliation,
        "sort": sort,
        "direction": direction,
        "per_page": per_page,
        "page": page
    }
    
    logger.info(f"Listando repositorios GitHub del usuario (PAT) - Página {page}")
    try:
        # Usar requests directamente con las cabeceras de GitHub PAT
        response = requests.get(url, headers=github_headers, params=params_query, timeout=DEFAULT_API_TIMEOUT)
        response.raise_for_status() # Lanza error para 4xx/5xx
        repos_data = response.json()
        logger.info(f"Encontrados {len(repos_data)} repositorios en la página.")
        return {"status": "success", "data": repos_data} # Devuelve la lista de repos de la página
    except requests.exceptions.RequestException as e:
        error_msg = f"Error al listar repositorios GitHub: {type(e).__name__}"
        details = str(e); status_code = 500
        if e.response is not None:
            status_code = e.response.status_code; error_msg += f" ({status_code})"
            try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        logger.error(error_msg, exc_info=True)
        return {"status": "error", "message": error_msg, "http_status": status_code, "details": details}
    except Exception as e: # Otros errores (ej. _get_github_auth_headers falló)
        logger.error(f"Error inesperado listando repositorios GitHub: {e}", exc_info=True)
        return {"status": "error", "message": f"Error inesperado: {type(e).__name__}", "details": str(e)}


def crear_issue(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Crea un nuevo issue en un repositorio específico.

    Args:
        parametros (Dict[str, Any]): Debe contener:
            'owner' (str): Dueño del repositorio (usuario u organización).
            'repo' (str): Nombre del repositorio.
            'title' (str): Título del issue.
            Opcional:
            'body' (str): Cuerpo/descripción del issue.
            'assignees' (List[str]): Logins de los usuarios a asignar.
            'labels' (List[str]): Nombres de las etiquetas a añadir.
            'milestone' (int): Número del milestone a asignar.
        headers (Dict[str, str]): Ignorado. Se usa GITHUB_PAT.

    Returns:
        Dict[str, Any]: {"status": "success", "data": {issue_creado}} o error.
    """
    owner: Optional[str] = parametros.get("owner")
    repo: Optional[str] = parametros.get("repo")
    title: Optional[str] = parametros.get("title")
    body_content: Optional[str] = parametros.get("body")
    assignees: Optional[List[str]] = parametros.get("assignees")
    labels: Optional[List[str]] = parametros.get("labels")
    milestone: Optional[int] = parametros.get("milestone")

    if not all([owner, repo, title]):
        return {"status": "error", "message": "Parámetros 'owner', 'repo', y 'title' son requeridos."}

    try:
        github_headers = _get_github_auth_headers()
    except ValueError as auth_err:
        return {"status": "error", "message": str(auth_err)}

    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/issues"
    payload: Dict[str, Any] = {"title": title}
    if body_content is not None: payload["body"] = body_content
    if assignees and isinstance(assignees, list): payload["assignees"] = assignees
    if labels and isinstance(labels, list): payload["labels"] = labels
    if milestone is not None:
        try: payload["milestone"] = int(milestone)
        except ValueError: return {"status": "error", "message": "'milestone' debe ser un número entero."}

    logger.info(f"Creando issue en GitHub repo '{owner}/{repo}' con título '{title}'")
    try:
        response = requests.post(url, headers=github_headers, json=payload, timeout=DEFAULT_API_TIMEOUT)
        response.raise_for_status()
        issue_data = response.json()
        logger.info(f"Issue #{issue_data.get('number')} creado exitosamente.")
        return {"status": "success", "data": issue_data}
    except requests.exceptions.RequestException as e:
        error_msg = f"Error al crear issue GitHub: {type(e).__name__}"
        details = str(e); status_code = 500
        if e.response is not None:
            status_code = e.response.status_code; error_msg += f" ({status_code})"
            try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        logger.error(error_msg, exc_info=True)
        return {"status": "error", "message": error_msg, "http_status": status_code, "details": details}
    except Exception as e:
        logger.error(f"Error inesperado creando issue GitHub: {e}", exc_info=True)
        return {"status": "error", "message": f"Error inesperado: {type(e).__name__}", "details": str(e)}

def listar_issues(parametros: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """
    Lista issues de un repositorio específico.

    Args:
        parametros (Dict[str, Any]): Debe contener 'owner', 'repo'.
            Opcional:
            'state' (str): 'open', 'closed', 'all'. Default 'open'.
            'assignee' (str): Login del asignado. '*' para cualquiera, 'none' para ninguno.
            'creator' (str): Login del creador.
            'mentioned' (str): Login del usuario mencionado.
            'labels' (str): Etiquetas separadas por coma.
            'sort' (str): 'created', 'updated', 'comments'. Default 'created'.
            'direction' (str): 'asc' o 'desc'. Default 'desc'.
            'since' (str): Fecha ISO 8601 para obtener issues actualizados desde entonces.
            'per_page' (int): Resultados por página. Default 30, max 100.
            'page' (int): Número de página a obtener. Default 1.
        headers (Dict[str, str]): Ignorado. Se usa GITHUB_PAT.

    Returns:
        Dict[str, Any]: {"status": "success", "data": [lista_issues]} o error.
    """
    owner: Optional[str] = parametros.get("owner")
    repo: Optional[str] = parametros.get("repo")
    if not owner or not repo:
        return {"status": "error", "message": "Parámetros 'owner' y 'repo' son requeridos."}

    try: github_headers = _get_github_auth_headers()
    except ValueError as auth_err: return {"status": "error", "message": str(auth_err)}

    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/issues"
    
    # Construir query params solo con los parámetros proporcionados
    params_query: Dict[str, Any] = {}
    allowed_params = ["state", "assignee", "creator", "mentioned", "labels", "sort", "direction", "since", "per_page", "page"]
    for param, value in parametros.items():
        if param in allowed_params and value is not None:
            if param == "per_page": value = min(int(value), 100) # Limitar per_page
            if param == "page": value = int(value)
            params_query[param] = value
    # Defaults si no se especifican
    params_query.setdefault("state", "open")
    params_query.setdefault("sort", "created")
    params_query.setdefault("direction", "desc")
    params_query.setdefault("per_page", 30)
    params_query.setdefault("page", 1)

    logger.info(f"Listando issues GitHub repo '{owner}/{repo}' con filtros: {params_query}")
    try:
        response = requests.get(url, headers=github_headers, params=params_query, timeout=DEFAULT_API_TIMEOUT)
        response.raise_for_status()
        issues_data = response.json()
        logger.info(f"Encontrados {len(issues_data)} issues en la página {params_query['page']}.")
        # La API de GitHub devuelve cabeceras 'Link' para paginación, no se maneja aquí por simplicidad.
        return {"status": "success", "data": issues_data}
    except requests.exceptions.RequestException as e:
        error_msg = f"Error al listar issues GitHub: {type(e).__name__}"
        details = str(e); status_code = 500
        if e.response is not None:
            status_code = e.response.status_code; error_msg += f" ({status_code})"
            try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        logger.error(error_msg, exc_info=True)
        return {"status": "error", "message": error_msg, "http_status": status_code, "details": details}
    except Exception as e:
        logger.error(f"Error inesperado listando issues GitHub: {e}", exc_info=True)
        return {"status": "error", "message": f"Error inesperado: {type(e).__name__}", "details": str(e)}

# --- Aquí se podrían añadir más acciones: obtener_issue, comentar_issue, listar_prs, etc. ---

# --- FIN DEL MÓDULO actions/github_actions.py ---