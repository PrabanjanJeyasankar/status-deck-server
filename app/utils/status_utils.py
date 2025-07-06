# ---
# File: app/utils/status_utils.py
# Purpose: Utility for determining monitor status based on HTTP status and response time
# ---

# ---
# Determine the health status of a monitor based on:
# - HTTP status code
# - Response time in milliseconds
# - Degraded response time threshold
#
# Returns:
# - "DOWN" if HTTP status indicates failure (outside 200-399)
# - "DEGRADED" if response time exceeds the degraded threshold
# - "UP" if the monitor is healthy
# ---
def determine_monitor_status(http_status_code: int, response_time: int, degraded_threshold: int) -> str:
    if http_status_code < 200 or http_status_code >= 400:
        return "DOWN"
    if response_time > degraded_threshold:
        return "DEGRADED"
    return "UP"
