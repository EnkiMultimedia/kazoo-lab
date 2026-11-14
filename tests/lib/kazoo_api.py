"""
Kazoo Crossbar API Client for E2E Testing
"""

import hashlib
import logging
import time
import requests
from typing import Optional

log = logging.getLogger(__name__)


class KazooAPIError(Exception):
    """Exception raised for Kazoo API errors."""
    pass


class KazooAPI:
    """Client for Kazoo Crossbar REST API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000/v2",
                 max_retries: int = 3, retry_delay: float = 1.0):
        self.base_url = base_url.rstrip("/")
        self.auth_token: Optional[str] = None
        self.account_id: Optional[str] = None
        self.session = requests.Session()
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make an authenticated API request with retry logic."""
        url = f"{self.base_url}{endpoint}"
        headers = kwargs.pop("headers", {})

        if self.auth_token:
            headers["X-Auth-Token"] = self.auth_token

        headers["Content-Type"] = "application/json"

        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(method, url, headers=headers, **kwargs)

                try:
                    data = response.json()
                except ValueError:
                    raise KazooAPIError(f"Invalid JSON response: {response.text}")

                if response.status_code >= 400:
                    error_msg = data.get("message", data.get("error", response.text))
                    raise KazooAPIError(f"API error {response.status_code}: {error_msg}")

                return data

            except (requests.ConnectionError, requests.Timeout) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    log.warning(f"Connection error on {method} {endpoint}, "
                                f"retrying in {delay:.1f}s (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(delay)
                continue

        # All retries exhausted
        raise KazooAPIError(f"Connection failed after {self.max_retries} attempts: {last_error}")

    def wait_for_api(self, timeout: int = 120, interval: int = 2) -> bool:
        """Wait for Kazoo API to become available."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                response = self.session.get(f"{self.base_url}/")
                if response.status_code in (200, 401):
                    return True
            except requests.RequestException:
                pass
            time.sleep(interval)
        raise KazooAPIError(f"Kazoo API not available after {timeout}s")

    def authenticate(self, username: str, password: str, account_name: str) -> str:
        """Authenticate and get auth token."""
        # Create MD5 hash of username:password
        credentials = f"{username}:{password}"
        creds_hash = hashlib.md5(credentials.encode()).hexdigest()

        data = {
            "data": {
                "credentials": creds_hash,
                "account_name": account_name
            }
        }

        response = self._request("PUT", "/user_auth", json=data)

        self.auth_token = response["auth_token"]
        self.account_id = response["data"]["account_id"]

        return self.auth_token

    def create_account(self, name: str, realm: Optional[str] = None) -> dict:
        """Create a new account."""
        if realm is None:
            realm = f"{name}.kazoo.local"

        data = {
            "data": {
                "name": name,
                "realm": realm
            }
        }

        response = self._request("PUT", "/accounts", json=data)
        return {
            "id": response["data"]["id"],
            "name": response["data"]["name"],
            "realm": response["data"]["realm"]
        }

    def delete_account(self, account_id: str) -> bool:
        """Delete an account."""
        try:
            self._request("DELETE", f"/accounts/{account_id}")
            return True
        except KazooAPIError:
            return False

    def create_device(self, account_id: str, name: str, username: str,
                      password: str, device_type: str = "sip_device") -> dict:
        """Create a SIP device."""
        data = {
            "data": {
                "name": name,
                "device_type": device_type,
                "sip": {
                    "username": username,
                    "password": password
                },
                "enabled": True
            }
        }

        response = self._request("PUT", f"/accounts/{account_id}/devices", json=data)
        return {
            "id": response["data"]["id"],
            "name": response["data"]["name"],
            "sip": {
                "username": response["data"]["sip"]["username"],
                "realm": response["data"]["sip"].get("realm")
            }
        }

    def create_callflow(self, account_id: str, numbers: list,
                        flow: dict, name: Optional[str] = None) -> dict:
        """Create a callflow."""
        if name is None:
            name = f"callflow_{numbers[0]}"

        data = {
            "data": {
                "name": name,
                "numbers": numbers,
                "flow": flow
            }
        }

        response = self._request("PUT", f"/accounts/{account_id}/callflows", json=data)
        return {
            "id": response["data"]["id"],
            "name": response["data"]["name"],
            "numbers": response["data"]["numbers"]
        }

    def get_cdrs(self, account_id: str, limit: int = 10) -> list:
        """Get CDRs for an account."""
        response = self._request("GET", f"/accounts/{account_id}/cdrs")
        return response.get("data", [])

    def get_cdr(self, account_id: str, cdr_id: str) -> dict:
        """Get a specific CDR."""
        response = self._request("GET", f"/accounts/{account_id}/cdrs/{cdr_id}")
        return response.get("data", {})

    def list_accounts(self) -> list:
        """List all accounts (requires super admin)."""
        response = self._request("GET", "/accounts")
        return response.get("data", [])

    def get_account(self, account_id: str) -> dict:
        """Get account details."""
        response = self._request("GET", f"/accounts/{account_id}")
        return response.get("data", {})

    # Phone Number Management

    def add_phone_number(self, account_id: str, phone_number: str) -> dict:
        """
        Add a phone number to an account.

        Args:
            account_id: The account ID
            phone_number: Phone number in E.164 format (e.g., +15551234567)

        Returns:
            dict with phone number details
        """
        # Normalize the phone number (remove + prefix for API)
        number = phone_number.lstrip("+")

        data = {
            "data": {}
        }

        response = self._request(
            "PUT",
            f"/accounts/{account_id}/phone_numbers/{number}/activate",
            json=data
        )
        return {
            "number": phone_number,
            "id": response["data"].get("id", number),
            "state": response["data"].get("pvt_state", "active")
        }

    def list_phone_numbers(self, account_id: str) -> list:
        """List all phone numbers for an account."""
        response = self._request("GET", f"/accounts/{account_id}/phone_numbers")
        numbers = response.get("data", {}).get("numbers", {})
        return list(numbers.keys())

    def delete_phone_number(self, account_id: str, phone_number: str) -> bool:
        """Delete a phone number from an account."""
        number = phone_number.lstrip("+")
        try:
            self._request("DELETE", f"/accounts/{account_id}/phone_numbers/{number}")
            return True
        except KazooAPIError:
            return False

    # Resource (Carrier) Management

    def create_resource(self, account_id: str, name: str, gateways: list,
                        rules: Optional[list] = None, flags: Optional[list] = None) -> dict:
        """
        Create a carrier resource for routing calls.

        Args:
            account_id: The account ID
            name: Resource name
            gateways: List of gateway configurations
            rules: Regex rules for number matching
            flags: Resource flags

        Returns:
            dict with resource details
        """
        if rules is None:
            rules = [{"regex": "^\\+?1?\\d{10}$"}]

        data = {
            "data": {
                "name": name,
                "gateways": gateways,
                "rules": rules,
                "flags": flags or [],
                "enabled": True
            }
        }

        response = self._request("PUT", f"/accounts/{account_id}/resources", json=data)
        return {
            "id": response["data"]["id"],
            "name": response["data"]["name"]
        }

    def create_global_resource(self, name: str, gateways: list,
                               rules: Optional[list] = None) -> dict:
        """
        Create a global (system-wide) carrier resource.

        This is used to accept inbound calls from carriers.
        """
        if rules is None:
            rules = [{"regex": "^\\+?1?\\d{10}$"}]

        data = {
            "data": {
                "name": name,
                "gateways": gateways,
                "rules": rules,
                "enabled": True,
                "weight_cost": 50
            }
        }

        response = self._request("PUT", "/resources", json=data)
        return {
            "id": response["data"]["id"],
            "name": response["data"]["name"]
        }

    # ecallmgr / FreeSWITCH Management

    def list_fs_nodes(self) -> list:
        """List connected FreeSWITCH nodes."""
        try:
            response = self._request("GET", "/sup/ecallmgr_maintenance/list_fs_nodes")
            return response.get("data", [])
        except KazooAPIError:
            return []

    def add_fs_node(self, node: str) -> bool:
        """
        Add a FreeSWITCH node to ecallmgr.

        Args:
            node: FreeSWITCH node in format "fs@hostname"

        Returns:
            True if successful
        """
        try:
            self._request("POST", f"/sup/ecallmgr_maintenance/add_fs_node/{node}")
            return True
        except KazooAPIError:
            return False

    def remove_fs_node(self, node: str) -> bool:
        """Remove a FreeSWITCH node from ecallmgr."""
        try:
            self._request("POST", f"/sup/ecallmgr_maintenance/remove_fs_node/{node}")
            return True
        except KazooAPIError:
            return False

    def wait_for_fs_node(self, node: str, timeout: int = 60) -> bool:
        """
        Wait for a FreeSWITCH node to be connected.

        Args:
            node: FreeSWITCH node name (can be partial match)
            timeout: Maximum seconds to wait

        Returns:
            True if node is connected
        """
        start = time.time()
        while time.time() - start < timeout:
            nodes = self.list_fs_nodes()
            for connected_node in nodes:
                if node in str(connected_node):
                    return True
            time.sleep(2)
        return False

    def get_system_status(self) -> dict:
        """Get system status including running applications."""
        try:
            response = self._request("GET", "/sup/kazoo_maintenance/which_apps")
            return {"apps": response.get("data", [])}
        except KazooAPIError as e:
            return {"error": str(e)}
