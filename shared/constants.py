import os

# --- Configuración General de la Aplicación ---
APP_NAME = os.environ.get("APP_NAME", "EliteDynamicsPro")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")


# --- Endpoints Base de APIs ---
GRAPH_API_BASE_URL = os.environ.get("GRAPH_API_ENDPOINT", "https://graph.microsoft.com/v1.0")
AZURE_MGMT_API_BASE_URL = os.environ.get("AZURE_MGMT_ENDPOINT", "https://management.azure.com")


# --- Scopes por Servicio ---
GRAPH_SCOPE = [os.environ.get("GRAPH_SCOPE_DEFAULT", "https://graph.microsoft.com/.default")]
# Opcional: Si alguna vez usas la versión beta de Graph
GRAPH_BETA_SCOPE = [os.environ.get("GRAPH_BETA_SCOPE_DEFAULT", "https://graph.microsoft.com/.default")]

AZURE_MGMT_SCOPE = [os.environ.get("AZURE_MGMT_SCOPE_DEFAULT", "https://management.azure.com/.default")]
POWER_BI_SCOPE = [os.environ.get("POWER_BI_SCOPE_DEFAULT", "https://analysis.windows.net/powerbi/api/.default")]

# Scope para Azure OpenAI
AZURE_OPENAI_RESOURCE_ENDPOINT = os.environ.get("AZURE_OPENAI_RESOURCE_ENDPOINT")
OPENAI_SCOPE = [f"{AZURE_OPENAI_RESOURCE_ENDPOINT}/.default"] if AZURE_OPENAI_RESOURCE_ENDPOINT else []


# --- Configuración Específica de Servicios ---
MEMORIA_LIST_NAME = os.environ.get("MEMORIA_LIST_NAME", "AsistenteMemoria")  # SharePoint lista para persistencia
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")


# --- Configuración externa para servicios no AAD (se recomienda Key Vault) ---
# GitHub
# GITHUB_PAT = os.environ.get("GITHUB_PAT")  # NO RECOMENDADO: Mejor usar Key Vault
# GITHUB_API_BASE_URL = "https://api.github.com"

# Forge (Autodesk)
# FORGE_CLIENT_ID = os.environ.get("FORGE_CLIENT_ID")  # NO RECOMENDADO: Mejor usar Key Vault
# FORGE_CLIENT_SECRET = os.environ.get("FORGE_CLIENT_SECRET")  # NO RECOMENDADO: Mejor usar Key Vault
# FORGE_API_BASE_URL = "https://developer.api.autodesk.com"


# --- Configuración General de API Calls ---
DEFAULT_API_TIMEOUT = int(os.environ.get("DEFAULT_API_TIMEOUT", "60"))  # Timeout en segundos


# --- Validaciones (Opcional pero Recomendado para producción) ---
if not GRAPH_SCOPE:
    raise ValueError("GRAPH_SCOPE no definido en las variables de entorno.")
if AZURE_OPENAI_RESOURCE_ENDPOINT and not OPENAI_SCOPE:
    raise ValueError("AZURE_OPENAI_RESOURCE_ENDPOINT está definido pero el scope no se pudo construir.")