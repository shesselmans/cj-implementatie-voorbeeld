"""
CJ Affiliate server-side conversion helper.

Reads an order dict (as received from the client HTML POST) and sends a
createOrders GraphQL mutation to the CJ Tracking API.

Required environment variables (or override the constants below):
  CJ_ENTERPRISE_ID      - Enterprise ID assigned by CJ's Client Integration team
  CJ_ACTION_TRACKER_ID  - Action Tracker ID assigned by CJ for the sale action
  CJ_ACCESS_TOKEN       - Personal Access Token from the CJ Developer Portal

Optional:
  CJ_ENDPOINT           - Defaults to the live endpoint. Use the test endpoint
                          (https://tracking.api.cj.com/graphqltest) during development.

Expected input dict (mirror of what the client HTML sends):
{
    "orderId":   "ORD-12345",
    "eventTime": "2026-06-14T13:00:00.000Z",   # ISO 8601 with Z (UTC)
    "amount":    399.90,
    "currency":  "EUR",
    "cjEvent":   "<value from cje cookie>",
    "coupon":    "SUMMER10",                    # optional
    "discount":  0.0,                           # optional, order-level
    "items": [
        {"sku": "RB3025-001/58", "unitPrice": 199.95, "quantity": 1, "discount": 0},
        {"sku": "RB2140-901",    "unitPrice": 199.95, "quantity": 1, "discount": 0}
    ]
}
"""

import json
import logging
import os

import requests
from dotenv import load_dotenv

# Load variables from .env (if present) before reading os.environ.
# Values already set in the real environment take precedence (override=False).
# Silently skip if the file is absent or unreadable.
try:
    load_dotenv(override=False)
except Exception:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration – set these in .env or as real environment variables
# ---------------------------------------------------------------------------
CJ_ENTERPRISE_ID     = os.environ.get("CJ_ENTERPRISE_ID", "")
CJ_ACTION_TRACKER_ID = os.environ.get("CJ_ACTION_TRACKER_ID", "")
CJ_ACCESS_TOKEN      = os.environ.get("CJ_ACCESS_TOKEN", "")
CJ_ENDPOINT_LIVE = "https://tracking.api.cj.com/graphql"
CJ_ENDPOINT_TEST = "https://tracking.api.cj.com/graphqltest"
CJ_ENDPOINT      = os.environ.get("CJ_ENDPOINT", CJ_ENDPOINT_TEST)

_missing = [
    name for name, val in {
        "CJ_ENTERPRISE_ID":     CJ_ENTERPRISE_ID,
        "CJ_ACTION_TRACKER_ID": CJ_ACTION_TRACKER_ID,
        "CJ_ACCESS_TOKEN":      CJ_ACCESS_TOKEN,
    }.items()
    if not val
]
if _missing:
    raise EnvironmentError(
        f"Missing required environment variable(s): {', '.join(_missing)}. "
        "Set them in .env or as real environment variables."
    )


# ---------------------------------------------------------------------------
# GraphQL literal serializer
#
# CJ's createOrders mutation uses inline argument syntax, not GraphQL variables,
# so values must be embedded as literals in the query string.
# Strings are JSON-quoted (handles escaping). Numbers are bare. Booleans are
# lowercase. Enums are unquoted. Lists and objects are recursively serialized.
# ---------------------------------------------------------------------------

def _gql_value(v):
    """Serialize a Python value to a GraphQL inline literal."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(float(v)) if isinstance(v, float) else str(v)
    if isinstance(v, str):
        # json.dumps gives us a properly escaped JSON string including quotes
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "[" + ", ".join(_gql_value(i) for i in v) + "]"
    if isinstance(v, dict):
        fields = ", ".join(f"{k}: {_gql_value(val)}" for k, val in v.items())
        return "{" + fields + "}"
    raise TypeError(f"Unsupported type for GraphQL serialization: {type(v)}")


def _gql_object(d):
    """Serialize a dict as a GraphQL object (no outer braces, for top-level args)."""
    return ", ".join(f"{k}: {_gql_value(v)}" for k, v in d.items())


# ---------------------------------------------------------------------------
# Mutation builder
# ---------------------------------------------------------------------------

def build_create_orders_mutation(order: dict, enterprise_id: str, action_tracker_id: str) -> str:
    """
    Build the createOrders GraphQL mutation string from an order dict.

    Raises ValueError when required fields are missing.
    """
    required = ("orderId", "eventTime", "currency", "cjEvent")
    missing = [f for f in required if not order.get(f)]
    if order.get("amount") is None:
        missing.append("amount")
    if missing:
        raise ValueError(f"Order is missing required fields: {missing}")

    try:
        tracker_id_value = int(action_tracker_id)
    except (ValueError, TypeError):
        raise ValueError(
            f"CJ_ACTION_TRACKER_ID must be a numeric string, got: {action_tracker_id!r}"
        )

    new_order: dict = {
        "enterpriseId":     enterprise_id,
        "actionTrackerId":  tracker_id_value,
        "eventTime":        order["eventTime"],
        "orderId":          str(order["orderId"]),
        "cjEvent":          order["cjEvent"],
        "amount":           float(order["amount"]),
        "currency":         order["currency"],
    }

    if order.get("discount") is not None and float(order["discount"]) != 0:
        new_order["discount"] = float(order["discount"])

    if order.get("coupon"):
        new_order["coupon"] = order["coupon"]

    if order.get("items"):
        new_order["items"] = [
            {
                "sku":       item["sku"],
                "unitPrice": float(item["unitPrice"]),
                "quantity":  int(item["quantity"]),
                "discount":  float(item.get("discount", 0)),
            }
            for item in order["items"]
        ]

    # Response fields we want back
    response_fields = """
        orders {
            submissionId
            orderReceivedTime
            advertiser { enterpriseId }
            actionTracker { id }
            eventTime
            orderId
            cjEvent
            amount
            discount
            items { unitPrice quantity sku discount }
            coupon
            currency
        }
        errors { message fields }"""

    mutation = (
        f"mutation {{ createOrders(newOrders: [{{{_gql_object(new_order)}}}])"
        f" {{{response_fields}}} }}"
    )
    return mutation


# ---------------------------------------------------------------------------
# HTTP call
# ---------------------------------------------------------------------------

def send_conversion(order: dict, endpoint: str = CJ_ENDPOINT) -> dict:
    """
    Send a conversion hit to the CJ Tracking API.

    Pass endpoint=CJ_ENDPOINT_TEST or CJ_ENDPOINT_LIVE to override the default.
    Returns the parsed JSON response dict on success.
    Raises RuntimeError when CJ reports order-level errors.
    Raises requests.HTTPError on HTTP-level failures.
    """
    mutation = build_create_orders_mutation(order, CJ_ENTERPRISE_ID, CJ_ACTION_TRACKER_ID)

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
        "CJ conversion accepted. submissionId=%s",
        orders[0].get("submissionId") if orders else "n/a",
    )
    return body


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")

    sample_order = {
        "orderId":   "ORD-20260614-001",
        "eventTime": "2026-06-14T13:00:00.000Z",
        "amount":    399.90,
        "currency":  "EUR",
        "cjEvent":   "7166ddf3b35b11eb834200a10a1eb972",   # example click ID
        "coupon":    "",
        "discount":  0.0,
        "items": [
            {
                "sku":       "RB3025-001/58",   # Ray-Ban Aviator Classic
                "unitPrice": 199.95,
                "quantity":  1,
                "discount":  0,
            },
            {
                "sku":       "RB2140-901",      # Ray-Ban Wayfarer Original
                "unitPrice": 199.95,
                "quantity":  1,
                "discount":  0,
            },
        ],
    }

    # Use sample values so the demo works without real credentials set
    demo_enterprise_id     = os.environ.get("CJ_ENTERPRISE_ID", "1113122")
    demo_action_tracker_id = os.environ.get("CJ_ACTION_TRACKER_ID", "18")

    print("--- GraphQL mutation ---")
    mutation = build_create_orders_mutation(
        sample_order, demo_enterprise_id, demo_action_tracker_id
    )
    print(mutation)
    print()

    # Uncomment to actually call CJ (needs real credentials in env vars):
    # result = send_conversion(sample_order)
    # print(json.dumps(result, indent=2))
