#!/usr/bin/env python3
"""
Kazoo E2E Test Runner

Supports multiple test scenarios:

1. Extension Test (call_extension):
   - Creates account, device, and callflow for extension 1000
   - SIPp calls extension 1000 (internal call)
   - Verifies call via CDR

2. Inbound DID Test (inbound_did):
   - Creates account and assigns a phone number
   - Creates callflow for that DID
   - SIPp simulates external carrier calling the DID
   - Verifies call lands and CDR is created
"""

import os
import sys
import time
import argparse
import logging

from lib.kazoo_api import KazooAPI, KazooAPIError
from lib.sipp_runner import SIPpRunner, SIPpRunnerInbound, wait_for_sip_port

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# Configuration from environment
KAZOO_API_URL = os.environ.get("KAZOO_API_URL", "http://kazoo-apps:8000/v2")
KAMAILIO_HOST = os.environ.get("KAMAILIO_HOST", "kamailio")
KAMAILIO_PORT = int(os.environ.get("KAMAILIO_PORT", "5060"))

# Master account credentials (from dev-setup)
MASTER_ACCOUNT = os.environ.get("MASTER_ACCOUNT", "admin")
MASTER_USER = os.environ.get("MASTER_USER", "admin")
MASTER_PASS = os.environ.get("MASTER_PASS", "admin123")

# Test configuration - Extension test
# Note: No underscores in account/user names - causes SIP URI parsing errors
TEST_ACCOUNT_NAME = os.environ.get("TEST_ACCOUNT_NAME", "e2etest")
TEST_DEVICE_NAME = os.environ.get("TEST_DEVICE_NAME", "sippdevice")
TEST_DEVICE_USER = os.environ.get("TEST_DEVICE_USER", "sippuser")
TEST_DEVICE_PASS = os.environ.get("TEST_DEVICE_PASS", "sipppass123")
TEST_EXTENSION = os.environ.get("TEST_EXTENSION", "1000")

# Test configuration - Inbound DID test
TEST_DID = os.environ.get("TEST_DID", "+15551234567")
TEST_CALLER_ID = os.environ.get("TEST_CALLER_ID", "+18005551212")
FREESWITCH_HOST = os.environ.get("FREESWITCH_HOST", "freeswitch")
FREESWITCH_EXTERNAL_PORT = int(os.environ.get("FREESWITCH_EXTERNAL_PORT", "11000"))
FREESWITCH_NODE = os.environ.get("FREESWITCH_NODE", "freeswitch@freeswitch")



def initialize_kazoo() -> bool:
    """
    Wait for Crossbar and check the master account.

    The stack is bootstrapped by deploy/scripts/e2e.sh (master account,
    FreeSWITCH node connected to ecallmgr), so this only checks Crossbar.
    """
    log.info("Initializing Kazoo...")
    api = KazooAPI(KAZOO_API_URL)
    try:
        api.wait_for_api(timeout=180)
        log.info("  Crossbar API is ready")
        api.authenticate(MASTER_USER, MASTER_PASS, MASTER_ACCOUNT)
        log.info("  Master account authentication successful")
    except KazooAPIError as e:
        log.error("  %s", e)
        log.error("  Bootstrap the stack first: deploy/scripts/e2e.sh")
        return False
    return True


def cleanup_existing_account(api: KazooAPI, account_name: str) -> bool:
    """
    Find and delete an existing test account by name.
    Returns True if account was found and deleted.
    """
    realm = f"{account_name}.kazoo.local"

    # Try to get account by authenticating to it (won't work without user)
    # Instead, try to create and get the validation error with account info
    try:
        account = api.create_account(account_name)
        # Account didn't exist before, but we just created it - delete it now
        # so setup_test_account can create it fresh with proper setup
        log.info("  Account didn't exist, deleting temporary creation...")
        api.delete_account(account["id"])
        time.sleep(1)
        return False
    except KazooAPIError as e:
        if "already in use" in str(e):
            # Account exists - we need to find and delete it
            log.info("  Found existing account: %s, attempting cleanup...", account_name)

            # Use search endpoint to find the account
            try:
                response = api.session.get(
                    f"{api.base_url}/search?t=account&q=name:{account_name}",
                    headers={
                        "X-Auth-Token": api.auth_token,
                        "Content-Type": "application/json"
                    }
                )
                if response.status_code == 200:
                    data = response.json().get("data", [])
                    for item in data:
                        if item.get("name") == account_name or item.get("realm") == realm:
                            account_id = item.get("id")
                            if account_id:
                                log.info("  Deleting existing account: %s", account_id)
                                api.delete_account(account_id)
                                time.sleep(1)  # Allow for propagation
                                return True
            except Exception as ex:
                log.debug("  Search failed: %s", ex)

            # Fallback: try sup command via API
            try:
                # Try to get account ID using sup endpoint
                response = api.session.get(
                    f"{api.base_url}/sup/crossbar_maintenance/find_account_by_realm/{realm}",
                    headers={
                        "X-Auth-Token": api.auth_token,
                        "Content-Type": "application/json"
                    }
                )
                if response.status_code == 200:
                    data = response.json().get("data")
                    if data:
                        account_id = data.get("id") or data
                        if isinstance(account_id, str) and len(account_id) == 32:
                            log.info("  Found account ID via sup: %s", account_id)
                            api.delete_account(account_id)
                            time.sleep(1)
                            return True
            except Exception as ex:
                log.debug("  Sup lookup failed: %s", ex)

            return False
        raise


def setup_test_account(api: KazooAPI) -> dict:
    """Create test account, device, and callflow."""
    # First, clean up any existing account with the same name
    cleanup_existing_account(api, TEST_ACCOUNT_NAME)

    log.info("Creating test account: %s", TEST_ACCOUNT_NAME)
    account = api.create_account(TEST_ACCOUNT_NAME)
    log.info("  Account ID: %s", account["id"])
    log.info("  Realm: %s", account["realm"])

    # Wait for account to be indexed in the aggregated accounts database
    # This is needed for realm-based routing lookup to work
    log.info("  Waiting for account indexing...")
    time.sleep(5)

    log.info("Creating SIP device: %s", TEST_DEVICE_NAME)
    device = api.create_device(
        account["id"],
        name=TEST_DEVICE_NAME,
        username=TEST_DEVICE_USER,
        password=TEST_DEVICE_PASS
    )
    log.info("  Device ID: %s", device["id"])
    log.info("  SIP Username: %s", device["sip"]["username"])

    log.info("Creating callflow for extension: %s", TEST_EXTENSION)
    # Simple callflow: answer -> hangup
    flow = {
        "module": "answer",
        "data": {},
        "children": {
            "_": {
                "module": "hangup",
                "data": {}
            }
        }
    }
    callflow = api.create_callflow(
        account["id"],
        numbers=[TEST_EXTENSION],
        flow=flow,
        name=f"E2E Test Callflow {TEST_EXTENSION}"
    )
    log.info("  Callflow ID: %s", callflow["id"])

    return {
        "account": account,
        "device": device,
        "callflow": callflow
    }


def run_sipp_test(account_realm: str, use_auth: bool = False) -> bool:
    """Run the SIPp scenario."""
    log.info("Running SIPp scenario...")
    log.info("  Target: %s:%d", KAMAILIO_HOST, KAMAILIO_PORT)
    log.info("  Extension: %s", TEST_EXTENSION)
    log.info("  Domain: %s", account_realm)
    log.info("  Auth: %s", "enabled" if use_auth else "disabled")

    # Get the scenario path - use invite_only for minimal Kamailio setup (no auth, no register)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    scenario_file = "register_call.xml" if use_auth else "invite_only.xml"
    scenario_path = os.path.join(script_dir, "scenarios", scenario_file)

    if not os.path.exists(scenario_path):
        log.error("Scenario file not found: %s", scenario_path)
        return False

    sipp = SIPpRunner(
        scenario=scenario_path,
        remote_host=KAMAILIO_HOST,
        remote_port=KAMAILIO_PORT,
        username=TEST_DEVICE_USER,
        password=TEST_DEVICE_PASS,
        domain=account_realm
    )

    result = sipp.run(calls=1, timeout=30)

    if result.success:
        log.info("SIPp scenario completed successfully!")
        return True
    else:
        log.error("SIPp scenario failed: %s", result.error)
        if result.stdout:
            log.debug("STDOUT:\n%s", result.stdout)
        if result.stderr:
            log.debug("STDERR:\n%s", result.stderr)
        return False


def verify_cdr(api: KazooAPI, account_id: str, max_wait: int = 30) -> bool:
    """Verify CDR was created for the test call."""
    log.info("Waiting for CDR to be written...")

    for i in range(max_wait):
        time.sleep(1)
        try:
            cdrs = api.get_cdrs(account_id)
            if cdrs:
                log.info("Found %d CDR(s)", len(cdrs))
                for cdr in cdrs:
                    log.info("  CDR ID: %s", cdr.get("id", "N/A"))
                    log.info("  Destination: %s", cdr.get("to", "N/A"))
                    log.info("  Hangup cause: %s", cdr.get("hangup_cause", "N/A"))
                    log.info("  Duration: %ss", cdr.get("duration_seconds", "N/A"))
                return True
        except KazooAPIError as e:
            log.debug("CDR query error (attempt %d): %s", i + 1, e)

    log.warning("No CDR found after %d seconds", max_wait)
    return False


def cleanup(api: KazooAPI, account_id: str):
    """Clean up test account."""
    log.info("Cleaning up test account: %s", account_id)
    try:
        api.delete_account(account_id)
        log.info("  Account deleted")
    except KazooAPIError as e:
        log.warning("  Could not delete account: %s", e)


# ==============================================================================
# Inbound DID Test
# ==============================================================================

def setup_inbound_did_test(api: KazooAPI) -> dict:
    """Create test account with phone number and callflow for inbound DID test."""
    account_name = f"{TEST_ACCOUNT_NAME}inbound"

    log.info("Creating test account: %s", account_name)
    account = api.create_account(account_name)
    log.info("  Account ID: %s", account["id"])
    log.info("  Realm: %s", account["realm"])

    # Wait for CouchDB views to be updated (realm lookup view)
    log.info("  Waiting for account indexing...")
    time.sleep(3)

    log.info("Adding phone number: %s", TEST_DID)
    try:
        phone_number = api.add_phone_number(account["id"], TEST_DID)
        log.info("  Phone number added: %s", phone_number["number"])
    except KazooAPIError as e:
        log.warning("  Could not add phone number via API: %s", e)
        log.info("  Continuing anyway - number may route via global settings")
        phone_number = {"number": TEST_DID}

    log.info("Creating callflow for DID: %s", TEST_DID)
    # Simple callflow: answer -> hangup
    flow = {
        "module": "answer",
        "data": {},
        "children": {
            "_": {
                "module": "hangup",
                "data": {}
            }
        }
    }

    # Use both with and without + prefix
    did_numbers = [TEST_DID, TEST_DID.lstrip("+")]
    callflow = api.create_callflow(
        account["id"],
        numbers=did_numbers,
        flow=flow,
        name=f"E2E Inbound DID {TEST_DID}"
    )
    log.info("  Callflow ID: %s", callflow["id"])
    log.info("  Numbers: %s", callflow["numbers"])

    return {
        "account": account,
        "phone_number": phone_number,
        "callflow": callflow
    }


def run_inbound_did_sipp_test() -> bool:
    """Run SIPp scenario simulating inbound carrier call."""
    log.info("Running inbound DID SIPp scenario...")
    log.info("  Target: %s:%d (FreeSWITCH external)", FREESWITCH_HOST, FREESWITCH_EXTERNAL_PORT)
    log.info("  DID: %s", TEST_DID)
    log.info("  Caller ID: %s", TEST_CALLER_ID)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    scenario_path = os.path.join(script_dir, "scenarios", "inbound_did.xml")

    if not os.path.exists(scenario_path):
        log.error("Scenario file not found: %s", scenario_path)
        return False

    sipp = SIPpRunnerInbound(
        scenario=scenario_path,
        remote_host=FREESWITCH_HOST,
        remote_port=FREESWITCH_EXTERNAL_PORT,
        did=TEST_DID,
        caller_id=TEST_CALLER_ID
    )

    result = sipp.run(calls=1, timeout=60)

    if result.success:
        log.info("Inbound DID SIPp scenario completed successfully!")
        return True
    else:
        log.error("Inbound DID SIPp scenario failed: %s", result.error)
        if result.stdout:
            log.info("STDOUT:\n%s", result.stdout)
        if result.stderr:
            log.info("STDERR:\n%s", result.stderr)
        return False


def test_inbound_did(api: KazooAPI, no_cleanup: bool = False) -> int:
    """
    Run the inbound DID test.

    This test simulates an external carrier sending a call to a phone number (DID)
    assigned to an account. The call should be routed to the callflow for that DID.
    """
    log.info("")
    log.info("=" * 60)
    log.info("INBOUND DID TEST")
    log.info("=" * 60)
    log.info("")

    # Setup
    log.info("Setting up inbound DID test...")
    test_data = None
    try:
        test_data = setup_inbound_did_test(api)
    except KazooAPIError as e:
        log.error("Setup failed: %s", e)
        return 1

    account_id = test_data["account"]["id"]

    try:
        # Check FreeSWITCH external port
        log.info("Checking FreeSWITCH external port...")
        if not wait_for_sip_port(FREESWITCH_HOST, FREESWITCH_EXTERNAL_PORT, timeout=10):
            log.error("FreeSWITCH external port not available at %s:%d",
                      FREESWITCH_HOST, FREESWITCH_EXTERNAL_PORT)
            return 1
        log.info("  FreeSWITCH external port ready")

        # Run SIPp
        log.info("Running inbound DID SIPp test...")
        sipp_success = run_inbound_did_sipp_test()
        if not sipp_success:
            log.error("Inbound DID SIPp test failed")
            return 1

        # Verify CDR
        log.info("Verifying CDR for inbound call...")
        if not verify_cdr(api, account_id):
            log.error("No CDR for the inbound DID call")
            return 1

        log.info("")
        log.info("=" * 60)
        log.info("INBOUND DID TEST PASSED!")
        log.info("=" * 60)
        return 0

    finally:
        if not no_cleanup and test_data:
            cleanup(api, account_id)


# ==============================================================================
# Extension Test (original test)
# ==============================================================================

def test_extension(api: KazooAPI, no_cleanup: bool = False, skip_sipp: bool = False) -> int:
    """Run the extension call test (original test)."""
    log.info("")
    log.info("=" * 60)
    log.info("EXTENSION CALL TEST")
    log.info("=" * 60)
    log.info("")

    # Setup test account
    log.info("Setting up test account...")
    test_data = None
    try:
        test_data = setup_test_account(api)
    except KazooAPIError as e:
        log.error("Setup failed: %s", e)
        return 1

    account_id = test_data["account"]["id"]
    account_realm = test_data["account"]["realm"]

    try:
        if skip_sipp:
            log.info("Skipping SIPp test (--skip-sipp)")
            log.info("  Account realm: %s", account_realm)
            log.info("  Device username: %s", TEST_DEVICE_USER)
            return 0

        # Wait for SIP port
        log.info("Checking SIP port...")
        if not wait_for_sip_port(KAMAILIO_HOST, KAMAILIO_PORT, timeout=10):
            log.error("SIP port not available at %s:%d", KAMAILIO_HOST, KAMAILIO_PORT)
            return 1
        log.info("  SIP port ready")

        # Run SIPp test
        log.info("Running SIPp test...")
        # the lab runs the 2600hz Kamailio config: register and call with auth
        sipp_success = run_sipp_test(account_realm, use_auth=True)
        if not sipp_success:
            log.error("SIPp test failed")
            return 1

        # Verify CDR
        log.info("Verifying CDR...")
        if not verify_cdr(api, account_id):
            log.error("No CDR for the extension call")
            return 1

        log.info("")
        log.info("=" * 60)
        log.info("EXTENSION CALL TEST PASSED!")
        log.info("=" * 60)
        return 0

    finally:
        if not no_cleanup and test_data:
            cleanup(api, account_id)


# ==============================================================================
# Main Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Kazoo E2E Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available tests:
  extension    - Test internal extension dialing (default)
  inbound_did  - Test inbound calls to a phone number (DID)
  all          - Run all tests

Examples:
  python run_tests.py                    # Run extension test
  python run_tests.py --test inbound_did # Run inbound DID test
  python run_tests.py --test all         # Run all tests
"""
    )
    parser.add_argument("--test", "-t", default="extension",
                        choices=["extension", "inbound_did", "all"],
                        help="Which test to run (default: extension)")
    parser.add_argument("--no-cleanup", action="store_true",
                        help="Don't clean up test account after test")
    parser.add_argument("--skip-sipp", action="store_true",
                        help="Skip SIPp test (setup only)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose output")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    log.info("=" * 60)
    log.info("Kazoo E2E Test Runner")
    log.info("=" * 60)
    log.info("")
    log.info("Configuration:")
    log.info("  Kazoo API: %s", KAZOO_API_URL)
    log.info("  Kamailio: %s:%d", KAMAILIO_HOST, KAMAILIO_PORT)
    log.info("  FreeSWITCH: %s:%d", FREESWITCH_HOST, FREESWITCH_EXTERNAL_PORT)
    log.info("  Master account: %s", MASTER_ACCOUNT)
    log.info("  Test(s): %s", args.test)
    log.info("")

    if not initialize_kazoo():
        log.error("Kazoo initialization failed")
        return 1

    # Initialize API client
    api = KazooAPI(KAZOO_API_URL)

    # Wait for Kazoo API
    log.info("Waiting for Kazoo API...")
    try:
        api.wait_for_api(timeout=180)
        log.info("  Kazoo API is ready")
    except KazooAPIError as e:
        log.error("  Failed: %s", e)
        return 1

    # Authenticate
    log.info("Authenticating...")
    try:
        api.authenticate(MASTER_USER, MASTER_PASS, MASTER_ACCOUNT)
        log.info("  Authenticated successfully")
    except KazooAPIError as e:
        log.error("  Failed: %s", e)
        return 1

    # Run selected test(s)
    results = {}

    if args.test in ("extension", "all"):
        results["extension"] = test_extension(
            api,
            no_cleanup=args.no_cleanup,
            skip_sipp=args.skip_sipp
        )

    if args.test in ("inbound_did", "all"):
        results["inbound_did"] = test_inbound_did(
            api,
            no_cleanup=args.no_cleanup
        )

    # Summary
    log.info("")
    log.info("=" * 60)
    log.info("TEST SUMMARY")
    log.info("=" * 60)

    all_passed = True
    for test_name, result in results.items():
        status = "PASSED" if result == 0 else "FAILED"
        log.info("  %s: %s", test_name, status)
        if result != 0:
            all_passed = False

    if all_passed:
        log.info("")
        log.info("ALL TESTS PASSED!")
        return 0
    else:
        log.info("")
        log.info("SOME TESTS FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
