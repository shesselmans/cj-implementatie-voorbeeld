"""
CJ Affiliate server-side conversion helper — afspraak (appointment) conversie.

Zelfde opzet als cj_conversion.py, maar voor de "afspraak"-actie in plaats van
een verkoop: geen productregels (items). De enterprise (company) ID blijft
hetzelfde, alleen de action tracker ID verschilt.

Vereiste environment variables (gedeeld met cj_conversion.py, zie .env):
  CJ_ENTERPRISE_ID      - zelfde enterprise ID als de transactieconversie
  CJ_ACCESS_TOKEN       - Personal Access Token van het CJ Developer Portal

Optioneel:
  CJ_ACTION_TRACKER_ID_AFSPRAAK  - Action Tracker ID voor de afspraak-actie
                                    (default: 515933)
  CJ_ENDPOINT                    - zelfde als bij cj_conversion.py
                                    (default: testomgeving)

Verwachte input dict (geen "items"):
{
    "orderId":   "AFS-12345",
    "eventTime": "2026-06-14T13:00:00.000Z",
    "amount":    3.0,
    "currency":  "EUR",
    "cjEvent":   "<value from cje cookie>"
}
"""

import json
import logging
import os

import requests

from cj_conversion import (
    CJ_ACCESS_TOKEN,
    CJ_ENDPOINT,
    CJ_ENDPOINT_TEST,
    CJ_ENTERPRISE_ID,
    build_create_orders_mutation,
)

logger = logging.getLogger(__name__)

CJ_ACTION_TRACKER_ID_AFSPRAAK = os.environ.get("CJ_ACTION_TRACKER_ID_AFSPRAAK", "515933")


def send_appointment_conversion(order: dict, endpoint: str = CJ_ENDPOINT) -> dict:
    """
    Send an appointment (afspraak) conversion hit to the CJ Tracking API.

    Same behaviour as cj_conversion.send_conversion, but always targets the
    appointment action tracker and drops any "items" from the order, since
    appointments don't carry a product list.
    """
    order = dict(order)
    order.pop("items", None)

    mutation = build_create_orders_mutation(
        order, CJ_ENTERPRISE_ID, CJ_ACTION_TRACKER_ID_AFSPRAAK
    )

    headers = {
        "Authorization": f"Bearer {CJ_ACCESS_TOKEN}",
        "Content-Type":  "application/json",
    }

    response = requests.post(
        endpoint,
        headers=headers,
        json={"query": mutation},
        timeout=10,
    )
    response.raise_for_status()

    body = response.json()
    logger.debug("CJ API response: %s", json.dumps(body, indent=2))

    errors = (
        body.get("data", {})
            .get("createOrders", {})
            .get("errors") or []
    )
    if errors:
        raise RuntimeError(f"CJ createOrders returned errors: {errors}")

    orders = (
        body.get("data", {})
            .get("createOrders", {})
            .get("orders", [])
    )
    logger.info(
        "CJ afspraak-conversie geaccepteerd. submissionId=%s",
        orders[0].get("submissionId") if orders else "n/a",
    )
    return body


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")

    sample_appointment = {
        "orderId":   "AFS-20260614-001",
        "eventTime": "2026-06-14T13:00:00.000Z",
        "amount":    3.0,
        "currency":  "EUR",
        "cjEvent":   "7166ddf3b35b11eb834200a10a1eb972",   # voorbeeld click ID
    }

    print("--- GraphQL mutation ---")
    mutation = build_create_orders_mutation(
        sample_appointment, CJ_ENTERPRISE_ID, CJ_ACTION_TRACKER_ID_AFSPRAAK
    )
    print(mutation)
    print()

    print("--- Versturen naar CJ testomgeving ---")
    # Expliciet CJ_ENDPOINT_TEST, ongeacht wat CJ_ENDPOINT in .env is, zodat
    # dit altijd tegen de testomgeving draait en nooit per ongeluk live gaat.
    result = send_appointment_conversion(sample_appointment, endpoint=CJ_ENDPOINT_TEST)
    print(json.dumps(result, indent=2))
