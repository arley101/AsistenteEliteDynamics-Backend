import logging
import requests
from azure.identity import DefaultAzureCredential, CredentialUnavailableError, ClientAuthenticationError
from typing import List, Optional, Any, Dict

# Importamos las constantes globales de la aplicación
from ..constants import APP_NAME, APP_VERSION, DEFAULT_API_TIMEOUT

# Configuración del logger para este módulo
logger = logging.getLogger(__name__)

class AuthenticatedHttpClient:
    """
    Un cliente HTTP que maneja automáticamente la adquisición de tokens de acceso
    usando DefaultAzureCredential y los inyecta en las solicitudes.
    """

    def __init__(self, credential: DefaultAzureCredential, default_timeout: int = DEFAULT_API_TIMEOUT):
        """
        Inicializa el cliente HTTP autenticado.

        Args:
            credential (DefaultAzureCredential): La credencial de Azure Identity a usar.
            default_timeout (int): Timeout predeterminado en segundos para las solicitudes HTTP.
        """
        if not isinstance(credential, DefaultAzureCredential):
            raise TypeError("Se requiere una instancia de DefaultAzureCredential.")
            
        self.credential = credential
        self.session = requests.Session()
        self.default_timeout = default_timeout

        # Configurar headers estándar para la sesión
        self.session.headers.update({
            'User-Agent': f'{APP_NAME}/{APP_VERSION}',
            'Accept': 'application/json'
            # 'Content-Type' se manejará por solicitud (especialmente para POST/PUT)
        })
        logger.info("AuthenticatedHttpClient inicializado con DefaultAzureCredential.")

    def _get_access_token(self, scope: List[str]) -> Optional[str]:
        """
        Obtiene un token de acceso para el scope especificado usando la credencial.

        Args:
            scope (List[str]): Lista de scopes para los cuales obtener el token (ej. ["https://graph.microsoft.com/.default"]).

        Returns:
            Optional[str]: El token de acceso como string, o None si falla la obtención.
        """
        if not scope:
            logger.error("Se requiere un scope para obtener el token de acceso.")
            return None
            
        try:
            logger.debug(f"Solicitando token para scope: {scope}")
            token_result = self.credential.get_token(*scope)
            logger.debug(f"Token obtenido exitosamente para scope: {scope}. Expiración: {token_result.expires_on}")
            return token_result.token
        except CredentialUnavailableError as e:
            logger.error(f"Error de credencial al obtener token para {scope}: {e}. Asegúrese de que la Identidad Administrada esté configurada o que haya iniciado sesión localmente.")
            return None
        except ClientAuthenticationError as e:
             logger.error(f"Error de autenticación del cliente al obtener token para {scope}: {e}. Verifique los permisos/configuración de la identidad.")
             return None
        except Exception as e:
            # Captura otros posibles errores de la librería de identidad
            logger.exception(f"Error inesperado al obtener token para {scope}: {e}")
            return None

    def request(self, method: str, url: str, scope: List[str], **kwargs: Any) -> requests.Response:
        """
        Realiza una solicitud HTTP autenticada.

        Args:
            method (str): Método HTTP (GET, POST, PUT, DELETE, PATCH).
            url (str): URL completa del endpoint.
            scope (List[str]): Lista de scopes requeridos para la API destino.
            **kwargs: Argumentos adicionales para requests.request (params, json, data, headers, timeout, etc.).

        Returns:
            requests.Response: El objeto de respuesta de la librería requests.

        Raises:
            ValueError: Si no se puede obtener el token de acceso.
            requests.exceptions.RequestException: Para errores relacionados con la solicitud HTTP.
        """
        # Obtener el token de acceso
        access_token = self._get_access_token(scope)
        if not access_token:
            raise ValueError(f"No se pudo obtener el token de acceso para el scope {scope}.")

        # Preparar headers para esta solicitud específica
        request_headers = kwargs.pop('headers', {}).copy() # Obtener headers de kwargs o crear dict vacío
        request_headers['Authorization'] = f'Bearer {access_token}'
        
        # Asegurar Content-Type si hay cuerpo (json o data)
        if 'json' in kwargs or 'data' in kwargs:
             if 'Content-Type' not in request_headers:
                  request_headers['Content-Type'] = 'application/json' # Predeterminado, ajustar si se usa 'data'

        # Usar timeout específico o el predeterminado
        timeout = kwargs.pop('timeout', self.default_timeout)

        logger.debug(f"Realizando solicitud {method} a {url} con scope {scope}")
        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=request_headers,
                timeout=timeout,
                **kwargs # Pasar el resto de los argumentos (params, json, data, etc.)
            )
            # Lanzar excepción para respuestas 4xx/5xx
            response.raise_for_status() 
            logger.debug(f"Solicitud {method} a {url} exitosa (Status: {response.status_code})")
            return response
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"Error HTTP en {method} {url}: {http_err.response.status_code} - {http_err.response.text[:500]}...") # Loguear inicio del cuerpo del error
            raise http_err # Relanzar para que el llamador lo maneje
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Error de conexión en {method} {url}: {req_err}")
            raise req_err # Relanzar
        except Exception as e:
             logger.exception(f"Error inesperado durante la solicitud {method} a {url}: {e}")
             # Podríamos querer relanzar una excepción personalizada aquí
             raise e 

    # Métodos convenientes para los verbos HTTP comunes
    def get(self, url: str, scope: List[str], **kwargs: Any) -> requests.Response:
        return self.request('GET', url, scope, **kwargs)

    def post(self, url: str, scope: List[str], **kwargs: Any) -> requests.Response:
        # Asegurar que Content-Type sea application/json si se usa 'json'
        if 'json' in kwargs and 'headers' not in kwargs:
            kwargs['headers'] = {'Content-Type': 'application/json'}
        elif 'json' in kwargs and 'Content-Type' not in kwargs.get('headers', {}):
             kwargs.setdefault('headers', {})['Content-Type'] = 'application/json'
             
        return self.request('POST', url, scope, **kwargs)

    def put(self, url: str, scope: List[str], **kwargs: Any) -> requests.Response:
        if 'json' in kwargs and 'headers' not in kwargs:
            kwargs['headers'] = {'Content-Type': 'application/json'}
        elif 'json' in kwargs and 'Content-Type' not in kwargs.get('headers', {}):
             kwargs.setdefault('headers', {})['Content-Type'] = 'application/json'
             
        return self.request('PUT', url, scope, **kwargs)

    def delete(self, url: str, scope: List[str], **kwargs: Any) -> requests.Response:
        return self.request('DELETE', url, scope, **kwargs)

    def patch(self, url: str, scope: List[str], **kwargs: Any) -> requests.Response:
        if 'json' in kwargs and 'headers' not in kwargs:
            kwargs['headers'] = {'Content-Type': 'application/json'}
        elif 'json' in kwargs and 'Content-Type' not in kwargs.get('headers', {}):
             kwargs.setdefault('headers', {})['Content-Type'] = 'application/json'
             
        return self.request('PATCH', url, scope, **kwargs)