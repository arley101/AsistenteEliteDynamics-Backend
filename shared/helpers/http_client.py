# EliteDynamicsPro_Local/shared/helpers/http_client.py
import logging
import requests
from azure.identity import DefaultAzureCredential, CredentialUnavailableError, ClientAuthenticationError
from typing import List, Optional, Any, Dict

# Importación directa de constants (desde la carpeta 'shared' en la raíz)
from shared import constants # 'constants.py' está en 'shared/'

logger = logging.getLogger(__name__)

class AuthenticatedHttpClient:
    def __init__(self, credential: DefaultAzureCredential, default_timeout: int = constants.DEFAULT_API_TIMEOUT):
        if not isinstance(credential, DefaultAzureCredential):
            raise TypeError("Se requiere una instancia de DefaultAzureCredential.")
        self.credential = credential
        self.session = requests.Session()
        self.default_timeout = default_timeout if default_timeout is not None else constants.DEFAULT_API_TIMEOUT
        self.session.headers.update({
            'User-Agent': f'{constants.APP_NAME}/{constants.APP_VERSION}', 
            'Accept': 'application/json'
        })
        logger.info("AuthenticatedHttpClient inicializado con DefaultAzureCredential.")

    def _get_access_token(self, scope: List[str]) -> Optional[str]:
        if not scope:
            logger.error("Se requiere un scope para obtener el token de acceso.")
            return None
        try:
            logger.debug(f"Solicitando token para scope: {scope}")
            token_result = self.credential.get_token(*scope)
            logger.debug(f"Token obtenido exitosamente para scope: {scope}. Expiración: {token_result.expires_on}")
            return token_result.token
        except CredentialUnavailableError as e:
            logger.error(f"Error de credencial al obtener token para {scope}: {e}.")
            return None
        except ClientAuthenticationError as e:
             logger.error(f"Error de autenticación del cliente al obtener token para {scope}: {e}.")
             return None
        except Exception as e:
            logger.exception(f"Error inesperado al obtener token para {scope}: {e}")
            return None

    def request(self, method: str, url: str, scope: List[str], **kwargs: Any) -> requests.Response:
        access_token = self._get_access_token(scope)
        if not access_token:
            raise ValueError(f"No se pudo obtener el token de acceso para el scope {scope}.")
        request_headers = kwargs.pop('headers', {}).copy()
        request_headers['Authorization'] = f'Bearer {access_token}'
        if 'json' in kwargs or 'data' in kwargs:
             if 'Content-Type' not in request_headers:
                  request_headers['Content-Type'] = 'application/json'
        timeout = kwargs.pop('timeout', self.default_timeout)
        logger.debug(f"Realizando solicitud {method} a {url} con scope {scope}")
        try:
            response = self.session.request(
                method=method, url=url, headers=request_headers, timeout=timeout, **kwargs
            )
            response.raise_for_status() 
            logger.debug(f"Solicitud {method} a {url} exitosa (Status: {response.status_code})")
            return response
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"Error HTTP en {method} {url}: {http_err.response.status_code} - {http_err.response.text[:500]}...")
            raise http_err
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Error de conexión en {method} {url}: {req_err}")
            raise req_err
        except Exception as e:
             logger.exception(f"Error inesperado durante la solicitud {method} a {url}: {e}")
             raise e 

    def get(self, url: str, scope: List[str], **kwargs: Any) -> requests.Response:
        return self.request('GET', url, scope, **kwargs)

    def post(self, url: str, scope: List[str], **kwargs: Any) -> requests.Response:
        if 'json_data' in kwargs and 'json' not in kwargs : 
            kwargs['json'] = kwargs.pop('json_data')
        if 'json' in kwargs and 'headers' not in kwargs:
            kwargs['headers'] = {'Content-Type': 'application/json'}
        elif 'json' in kwargs and 'Content-Type' not in kwargs.get('headers', {}):
             kwargs.setdefault('headers', {})['Content-Type'] = 'application/json'
        return self.request('POST', url, scope, **kwargs)

    def put(self, url: str, scope: List[str], **kwargs: Any) -> requests.Response:
        if 'json_data' in kwargs and 'json' not in kwargs : 
            kwargs['json'] = kwargs.pop('json_data')
        if 'json' in kwargs and 'headers' not in kwargs:
            kwargs['headers'] = {'Content-Type': 'application/json'}
        elif 'json' in kwargs and 'Content-Type' not in kwargs.get('headers', {}):
             kwargs.setdefault('headers', {})['Content-Type'] = 'application/json'
        return self.request('PUT', url, scope, **kwargs)

    def delete(self, url: str, scope: List[str], **kwargs: Any) -> requests.Response:
        return self.request('DELETE', url, scope, **kwargs)

    def patch(self, url: str, scope: List[str], **kwargs: Any) -> requests.Response:
        if 'json_data' in kwargs and 'json' not in kwargs : 
            kwargs['json'] = kwargs.pop('json_data')
        if 'json' in kwargs and 'headers' not in kwargs:
            kwargs['headers'] = {'Content-Type': 'application/json'}
        elif 'json' in kwargs and 'Content-Type' not in kwargs.get('headers', {}):
             kwargs.setdefault('headers', {})['Content-Type'] = 'application/json'
        return self.request('PATCH', url, scope, **kwargs)