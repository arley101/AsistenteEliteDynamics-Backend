# MyHttpTrigger/actions/github_actions.py
import logging
import requests # Usaremos requests directamente para la API de GitHub
import json
import os
from typing import Dict, List, Optional, Any

# Importar constantes compartidas
from ..shared import constants # Para DEFAULT_API_TIMEOUT, y APP_NAME para logger si se desea

logger = logging.getLogger(__name__)

# --- Constantes y Configuración Específica para GitHub API ---
GITHUB_API_BASE_URL = "https://api.github.com"
# Leer PAT de variable de entorno.
# ¡IMPORTANTE! En producción, configurar esto como App Setting en Azure, idealmente desde Key Vault.
GITHUB_PAT = os.environ.get("GITHUB_PAT")

# --- Helper de Autenticación (Específico para GitHub PAT) ---
def _get_github_auth_headers() -> Dict[str, str]:
    """Construye las cabeceras de autenticación para GitHub API usando PAT."""
    if not GITHUB_PAT:
        msg = "Variable de entorno 'GITHUB_PAT' no configurada. No se puede autenticar con GitHub API."
        logger.critical(msg)
        # Este error es crítico, la función que llama debe manejarlo o fallar.
        raise ValueError(msg)

    headers = {
        'Authorization': f'Bearer {GITHUB_PAT}',
        'Accept': 'application/vnd.github.v3+json',
        'X-GitHub-Api-Version': '2022-11-28'
    }
    return headers

# ---- FUNCIONES DE ACCIÓN PARA GITHUB (Refactorizadas) ----
# El parámetro 'client: AuthenticatedHttpClient' SE IGNORA aquí.

def github_list_repos(client: Optional[AuthenticatedHttpClient], params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lista los repositorios del usuario autenticado (asociado al PAT).
    El parámetro 'client' es ignorado para esta acción.
    """
    # Parámetros de la API de GitHub
    visibility: str = params.get('visibility', 'all')
    affiliation: str = params.get('affiliation', 'owner,collaborator')
    sort: str = params.get('sort', 'pushed')
    direction: str = params.get('direction', 'desc')
    per_page: int = min(int(params.get('per_page', 30)), 100)
    page: int = int(params.get('page', 1))

    try:
        github_headers = _get_github_auth_headers()
    except ValueError as auth_err:
        return {"status": "error", "message": str(auth_err), "http_status": 401} # Error de autenticación

    url = f"{GITHUB_API_BASE_URL}/user/repos"
    query_api_params = {
        "visibility": visibility,
        "affiliation": affiliation,
        "sort": sort,
        "direction": direction,
        "per_page": per_page,
        "page": page
    }
    
    logger.info(f"Listando repositorios GitHub del usuario (PAT) - Página {page}")
    try:
        response = requests.get(url, headers=github_headers, params=query_api_params, timeout=constants.DEFAULT_API_TIMEOUT)
        response.raise_for_status() 
        repos_data = response.json()
        logger.info(f"Encontrados {len(repos_data)} repositorios en la página.")
        return {"status": "success", "data": repos_data}
    except requests.exceptions.RequestException as e:
        error_msg = f"Error al listar repositorios GitHub: {type(e).__name__}"
        details = str(e); status_code_resp = 500
        if e.response is not None:
            status_code_resp = e.response.status_code; error_msg += f" ({status_code_resp})"
            try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        logger.error(error_msg, exc_info=False) # No loguear exc_info para errores HTTP manejados
        return {"status": "error", "message": error_msg, "http_status": status_code_resp, "details": details}
    except Exception as e:
        logger.error(f"Error inesperado listando repositorios GitHub: {e}", exc_info=True)
        return {"status": "error", "message": f"Error inesperado: {type(e).__name__}", "details": str(e)}


def github_create_issue(client: Optional[AuthenticatedHttpClient], params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Crea un nuevo issue en un repositorio específico.
    El parámetro 'client' es ignorado.
    """
    owner: Optional[str] = params.get("owner")
    repo: Optional[str] = params.get("repo")
    title: Optional[str] = params.get("title")
    body_content: Optional[str] = params.get("body")
    assignees: Optional[List[str]] = params.get("assignees")
    labels: Optional[List[str]] = params.get("labels")
    milestone_param: Optional[Union[int, str]] = params.get("milestone") # Puede ser int o str

    if not all([owner, repo, title]):
        return {"status": "error", "message": "Parámetros 'owner', 'repo', y 'title' son requeridos.", "http_status": 400}

    try:
        github_headers = _get_github_auth_headers()
    except ValueError as auth_err:
        return {"status": "error", "message": str(auth_err), "http_status": 401}

    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/issues"
    payload: Dict[str, Any] = {"title": title}
    if body_content is not None: payload["body"] = body_content
    if assignees and isinstance(assignees, list): payload["assignees"] = assignees
    if labels and isinstance(labels, list): payload["labels"] = labels
    if milestone_param is not None:
        try: 
            payload["milestone"] = int(milestone_param)
        except ValueError: 
            return {"status": "error", "message": "'milestone' debe ser un número entero.", "http_status": 400}

    logger.info(f"Creando issue en GitHub repo '{owner}/{repo}' con título '{title}'")
    try:
        response = requests.post(url, headers=github_headers, json=payload, timeout=constants.DEFAULT_API_TIMEOUT)
        response.raise_for_status()
        issue_data = response.json()
        logger.info(f"Issue #{issue_data.get('number')} creado exitosamente.")
        return {"status": "success", "data": issue_data}
    except requests.exceptions.RequestException as e:
        error_msg = f"Error al crear issue GitHub: {type(e).__name__}"
        details = str(e); status_code_resp = 500
        if e.response is not None:
            status_code_resp = e.response.status_code; error_msg += f" ({status_code_resp})"
            try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        logger.error(error_msg, exc_info=False)
        return {"status": "error", "message": error_msg, "http_status": status_code_resp, "details": details}
    except Exception as e:
        logger.error(f"Error inesperado creando issue GitHub: {e}", exc_info=True)
        return {"status": "error", "message": f"Error inesperado: {type(e).__name__}", "details": str(e)}

def github_list_issues(client: Optional[AuthenticatedHttpClient], params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lista issues de un repositorio específico.
    El parámetro 'client' es ignorado.
    """
    owner: Optional[str] = params.get("owner")
    repo: Optional[str] = params.get("repo")
    if not owner or not repo:
        return {"status": "error", "message": "Parámetros 'owner' y 'repo' son requeridos.", "http_status": 400}

    try: 
        github_headers = _get_github_auth_headers()
    except ValueError as auth_err: 
        return {"status": "error", "message": str(auth_err), "http_status": 401}

    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/issues"
    
    query_api_params: Dict[str, Any] = {}
    allowed_api_params = ["state", "assignee", "creator", "mentioned", "labels", "sort", "direction", "since", "per_page", "page"]
    for param_key, value in params.items():
        if param_key in allowed_api_params and value is not None:
            if param_key == "per_page": value = min(int(value), 100)
            if param_key == "page": value = int(value)
            query_api_params[param_key] = value
    
    # Establecer defaults si no se proporcionan
    query_api_params.setdefault("state", "open")
    query_api_params.setdefault("sort", "created")
    query_api_params.setdefault("direction", "desc")
    query_api_params.setdefault("per_page", 30)
    query_api_params.setdefault("page", 1)

    logger.info(f"Listando issues GitHub repo '{owner}/{repo}' con filtros: {query_api_params}")
    try:
        response = requests.get(url, headers=github_headers, params=query_api_params, timeout=constants.DEFAULT_API_TIMEOUT)
        response.raise_for_status()
        issues_data = response.json()
        logger.info(f"Encontrados {len(issues_data)} issues en la página {query_api_params['page']}.")
        return {"status": "success", "data": issues_data}
    except requests.exceptions.RequestException as e:
        error_msg = f"Error al listar issues GitHub: {type(e).__name__}"
        details = str(e); status_code_resp = 500
        if e.response is not None:
            status_code_resp = e.response.status_code; error_msg += f" ({status_code_resp})"
            try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        logger.error(error_msg, exc_info=False)
        return {"status": "error", "message": error_msg, "http_status": status_code_resp, "details": details}
    except Exception as e:
        logger.error(f"Error inesperado listando issues GitHub: {e}", exc_info=True)
        return {"status": "error", "message": f"Error inesperado: {type(e).__name__}", "details": str(e)}

# --- Aquí se podrían añadir más acciones: github_get_issue, github_add_comment_issue, github_list_prs, etc. ---
# --- mapeadas en mapping_actions.py y usando el mismo patrón. ---