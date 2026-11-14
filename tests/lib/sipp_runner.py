"""
SIPp Test Runner for Kazoo E2E Tests
"""

import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class SIPpResult:
    """Result of a SIPp test run."""
    success: bool
    return_code: int
    stdout: str
    stderr: str
    error: Optional[str] = None


class SIPpRunner:
    """Wrapper for running SIPp scenarios."""

    def __init__(
        self,
        scenario: str,
        remote_host: str,
        remote_port: int = 5060,
        local_ip: Optional[str] = None,
        local_port: int = 5061,
        username: Optional[str] = None,
        password: Optional[str] = None,
        domain: Optional[str] = None,
        transport: str = "u1"  # UDP
    ):
        self.scenario = scenario
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.local_ip = local_ip
        self.local_port = local_port
        self.username = username
        self.password = password
        self.domain = domain or remote_host
        self.transport = transport

    def _create_csv_injection(self, output_path: str) -> str:
        """Create CSV injection file for SIPp variables."""
        lines = [
            "SEQUENTIAL",
            f"{self.username};{self.password};{self.domain}"
        ]
        with open(output_path, "w") as f:
            f.write("\n".join(lines))
        return output_path

    def run(
        self,
        calls: int = 1,
        rate: float = 1.0,
        timeout: int = 30,
        max_retrans: int = 5
    ) -> SIPpResult:
        """
        Run the SIPp scenario.

        Args:
            calls: Number of calls to make
            rate: Call rate (calls per second)
            timeout: Timeout in seconds
            max_retrans: Max retransmissions

        Returns:
            SIPpResult with success status and output
        """
        # Resolve hostname to IPv4 address to avoid IPv6 issues in Docker
        import socket
        try:
            remote_ip = socket.gethostbyname(self.remote_host)
        except socket.gaierror:
            remote_ip = self.remote_host

        # Build SIPp command
        cmd = [
            "sipp",
            f"{remote_ip}:{self.remote_port}",
            "-sf", self.scenario,
            "-m", str(calls),
            "-r", str(rate),
            "-recv_timeout", str(timeout * 1000),  # ms
            "-max_retrans", str(max_retrans),
            "-t", self.transport,
            "-p", str(self.local_port),
        ]

        # Add local IP if specified
        if self.local_ip:
            cmd.extend(["-i", self.local_ip])

        # A fresh Call-ID per run: the registrar rejects a REGISTER that
        # reuses a Call-ID with a lower CSeq than the stored one
        cmd.extend(["-cid_str", "%u-%p@%s-" + uuid.uuid4().hex[:12]])

        # Create injection file if we have credentials
        csv_file = None
        if self.username:
            csv_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", delete=False
            )
            csv_file.write("SEQUENTIAL\n")
            csv_file.write(f"{self.username};{self.password or ''};{self.domain}\n")
            csv_file.close()
            cmd.extend(["-inf", csv_file.name])
            # Add authentication credentials for [authentication] keyword
            cmd.extend(["-au", self.username])
            if self.password:
                cmd.extend(["-ap", self.password])

        # Add additional options (no trace files to avoid read-only fs issues)
        cmd.extend([
            "-nostdin",
        ])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 10,
                cwd=os.path.dirname(self.scenario) if os.path.dirname(self.scenario) else None
            )

            success = result.returncode == 0
            error = None

            if not success:
                # Parse error from stderr or stdout
                if "Connection refused" in result.stderr:
                    error = "Connection refused - SIP server not reachable"
                elif "timeout" in result.stderr.lower():
                    error = "Timeout waiting for response"
                elif result.returncode == 1:
                    error = "Call failed - check scenario logs"
                else:
                    error = f"SIPp exited with code {result.returncode}"

            return SIPpResult(
                success=success,
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                error=error
            )

        except subprocess.TimeoutExpired:
            return SIPpResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr="",
                error=f"SIPp timed out after {timeout}s"
            )

        except FileNotFoundError:
            return SIPpResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr="",
                error="SIPp not found - is it installed?"
            )

        finally:
            # Cleanup temp file
            if csv_file and os.path.exists(csv_file.name):
                os.unlink(csv_file.name)


class SIPpRunnerInbound:
    """
    Wrapper for running inbound DID SIPp scenarios.

    This runner simulates an external carrier calling a DID (phone number).
    It sends calls to FreeSWITCH's external profile (typically port 5080).
    """

    def __init__(
        self,
        scenario: str,
        remote_host: str,
        remote_port: int = 5080,
        local_ip: Optional[str] = None,
        local_port: int = 5062,
        did: str = "+15551234567",
        caller_id: str = "+18005551212",
        transport: str = "u1"  # UDP
    ):
        self.scenario = scenario
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.local_ip = local_ip
        self.local_port = local_port
        self.did = did
        self.caller_id = caller_id
        self.transport = transport

    def run(
        self,
        calls: int = 1,
        rate: float = 1.0,
        timeout: int = 60,
        max_retrans: int = 5
    ) -> SIPpResult:
        """
        Run the inbound DID SIPp scenario.

        Args:
            calls: Number of calls to make
            rate: Call rate (calls per second)
            timeout: Timeout in seconds
            max_retrans: Max retransmissions

        Returns:
            SIPpResult with success status and output
        """
        # Resolve hostname to IPv4 address to avoid IPv6 issues in Docker
        import socket
        try:
            remote_ip = socket.gethostbyname(self.remote_host)
        except socket.gaierror:
            remote_ip = self.remote_host

        # Build SIPp command
        cmd = [
            "sipp",
            f"{remote_ip}:{self.remote_port}",
            "-sf", self.scenario,
            "-m", str(calls),
            "-r", str(rate),
            "-recv_timeout", str(timeout * 1000),  # ms
            "-max_retrans", str(max_retrans),
            "-t", self.transport,
            "-p", str(self.local_port),
            # Set scenario variables
            "-set", "did", self.did,
            "-set", "caller_id", self.caller_id,
        ]

        # Add local IP if specified
        if self.local_ip:
            cmd.extend(["-i", self.local_ip])

        # Add additional options (no trace files to avoid read-only fs issues)
        cmd.extend([
            "-nostdin",
        ])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 30,
                cwd=os.path.dirname(self.scenario) if os.path.dirname(self.scenario) else None
            )

            success = result.returncode == 0
            error = None

            if not success:
                # Parse error from stderr or stdout
                if "Connection refused" in result.stderr:
                    error = "Connection refused - FreeSWITCH external port not reachable"
                elif "timeout" in result.stderr.lower():
                    error = "Timeout waiting for response"
                elif result.returncode == 1:
                    error = "Call failed - check scenario logs"
                else:
                    error = f"SIPp exited with code {result.returncode}"

            return SIPpResult(
                success=success,
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                error=error
            )

        except subprocess.TimeoutExpired:
            return SIPpResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr="",
                error=f"SIPp timed out after {timeout}s"
            )

        except FileNotFoundError:
            return SIPpResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr="",
                error="SIPp not found - is it installed?"
            )


def wait_for_sip_port(host: str, port: int, timeout: int = 30) -> bool:
    """Wait for SIP port to be available."""
    import socket
    import time

    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1)
            sock.connect((host, port))
            sock.close()
            return True
        except (socket.error, socket.timeout):
            time.sleep(1)
    return False
