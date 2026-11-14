# SIPp E2E Test Container for Kazoo
# Contains Python 3.11 + SIPp for automated call testing

FROM python:3.11-slim

# Install SIPp and utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    sip-tester \
    curl \
    netcat-openbsd \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Create test directory
WORKDIR /tests

# Copy test files (context is tests/e2e/)
COPY lib/ /tests/lib/
COPY scenarios/ /tests/scenarios/
COPY run_tests.py /tests/

# Default entry point
ENTRYPOINT ["python", "run_tests.py"]
