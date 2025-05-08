# MyHttpTrigger/shared/constants.py
import os

# --- Application Info ---
APP_NAME = os.environ.get("APP_NAME", "EliteDynamicsPro")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")

# --- Microsoft Graph API ---
GRAPH_API_BASE_URL = os.environ.get("GRAPH_API_ENDPOINT", "https://graph.microsoft.com/v1.0")
GRAPH_API_DEFAULT_SCOPE = [os.environ.get("GRAPH_SCOPE", "https://graph.microsoft.com/.default")]

# --- Azure OpenAI (via AAD Auth) ---
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT") # Ej: https://tu-recurso.openai.azure.com
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview") # Revisa tu versión
AZURE_OPENAI_DEFAULT_SCOPE = [os.environ.get("AZURE_OPENAI_SCOPE", "https://cognitiveservices.azure.com/.default")]

# --- Power BI API (via AAD Client Credentials) ---
PBI_API_BASE_URL = os.environ.get("PBI_API_BASE_URL", "https://api.powerbi.com/v1.0/myorg")
PBI_API_DEFAULT_SCOPE = [os.environ.get("PBI_API_SCOPE", "https://analysis.windows.net/powerbi/api/.default")]
# PBI_CLIENT_ID, PBI_CLIENT_SECRET, PBI_TENANT_ID se leen de os.environ directamente en el módulo de acción

# --- Azure Management API (for Power Automate/Logic Apps) ---
AZURE_MGMT_BASE_URL = os.environ.get("AZURE_MGMT_BASE_URL", "https://management.azure.com")
AZURE_MGMT_DEFAULT_SCOPE = [os.environ.get("AZURE_MGMT_SCOPE", "https://management.azure.com/.default")]
LOGIC_APPS_API_VERSION = os.environ.get("LOGIC_APPS_API_VERSION", "2019-05-01")
# AZURE_CLIENT_ID_MGMT, AZURE_CLIENT_SECRET_MGMT, AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP se leen de os.environ directamente en el módulo de acción

# --- SharePoint Config Defaults ---
SHAREPOINT_DEFAULT_SITE_ID = os.environ.get('SHAREPOINT_DEFAULT_SITE_ID') # Ej: mytenant.sharepoint.com,GUID,GUID o 'root'
SHAREPOINT_DEFAULT_DRIVE_NAME_OR_ID = os.environ.get('SHAREPOINT_DEFAULT_DRIVE_NAME_OR_ID', 'Documents')
SHAREPOINT_MEMORY_LIST_NAME = os.environ.get('SHAREPOINT_MEMORY_LIST_NAME', 'AsistenteMemoriaPersistente')

# --- Timeouts (segundos) ---
DEFAULT_API_TIMEOUT = int(os.environ.get("DEFAULT_API_TIMEOUT", "60"))
AZURE_MGMT_API_DEFAULT_TIMEOUT = int(os.environ.get("AZURE_MGMT_API_DEFAULT_TIMEOUT", "90"))
PBI_API_TIMEOUT = int(os.environ.get("PBI_API_TIMEOUT", "90"))
OPENAI_API_TIMEOUT = int(os.environ.get("OPENAI_API_TIMEOUT", "120"))

# --- GitHub API (via PAT) ---
GITHUB_API_BASE_URL = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
# GITHUB_PAT se lee directamente de os.environ en el módulo de acción

# --- Logging Config Placeholder (No activa logging aquí, solo referencia) ---
# LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", "INFO").upper()