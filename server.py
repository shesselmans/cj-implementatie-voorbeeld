"""
Pearle CJ conversion server.

Receives the order JSON posted by the client HTML and forwards it to the
CJ Affiliate Tracking API via server-side GraphQL call.

Usage (development):
    python server.py

The server reads credentials from .env (via cj_conversion.py / python-dotenv).

Endpoints:
    GET  /              - health check
    POST /cj-conversion - accepts the order payload, calls CJ, returns result
"""

import json
import logging
import os

# Tell Flask not to load dotenv itself; we handle it via python-dotenv in
# cj_conversion.py so the credentials are already in os.environ when Flask starts.
os.environ.setdefault("FLASK_SKIP_DOTENV", "1")

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from cj_appointment_conversion import send_appointment_conversion
from cj_conversion import send_conversion, CJ_ENDPOINT_LIVE, CJ_ENDPOINT_TEST

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# CORS: allow the Pearle confirmation page to call this server during testing.
# In production, restrict origins to the exact Pearle domain(s).
CORS(app, supports_credentials=True, origins=["https://www.pearle.nl", "http://localhost"])


@app.get("/")
def health():
    """Simple health-check so you can verify the server is up."""
    return jsonify({"status": "ok", "service": "pearle-cj-conversion"})


@app.get("/test")
def test_page():
    """Serve the client HTML for local testing."""
    return send_from_directory(".", "conversion-client.html")


@app.get("/test-afspraak")
def test_appointment_page():
    """Serve the appointment client HTML for local testing."""
    return send_from_directory(".", "conversion-client-afspraak.html")


@app.post("/cj-conversion")
def cj_conversion():
    """
    Accept the order payload from the client HTML and forward to CJ.

    Expected JSON body (mirrors what conversion-client.html sends):
    {
        "orderId":   "ORD-001",
        "eventTime": "2026-06-14T13:00:00.000Z",
        "amount":    399.90,
        "currency":  "EUR",
        "cjEvent":   "<cje cookie value>",
        "coupon":    "SUMMER10",        // optional
        "discount":  0.0,               // optional
        "items": [
            {"sku": "RB3025-001/58", "unitPrice": 199.95, "quantity": 1, "discount": 0},
            {"sku": "RB2140-901",    "unitPrice": 199.95, "quantity": 1, "discount": 0}
        ]
    }
    """
    order = request.get_json(silent=True)

    if not order:
        logger.warning("Received request with no JSON body.")
        return jsonify({"error": "Request body must be JSON."}), 400

    required = ("orderId", "eventTime", "amount", "currency", "cjEvent")
    missing = [f for f in required if not order.get(f)]
    if missing:
        logger.warning("Missing required fields: %s", missing)
        return jsonify({"error": "Missing required fields.", "fields": missing}), 400

    demo = bool(order.pop("demo", False))
    order.pop("affiliateName", None)   # niet doorgeven aan CJ

    endpoint = CJ_ENDPOINT_TEST if demo else CJ_ENDPOINT_LIVE
    logger.info("demo=%s → endpoint: %s", demo, endpoint)

    try:
        result = send_conversion(order, endpoint=endpoint)
        logger.info("Conversion forwarded to CJ. orderId=%s", order.get("orderId"))
        return jsonify(result), 200

    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        return jsonify({"error": "Server configuration error.", "detail": str(exc)}), 500

    except RuntimeError as exc:
        # CJ returned order-level errors (e.g. duplicate orderId)
        logger.error("CJ rejected the order: %s", exc)
        return jsonify({"error": "CJ rejected the conversion.", "detail": str(exc)}), 422

    except Exception as exc:
        logger.exception("Unexpected error forwarding conversion to CJ.")
        return jsonify({"error": "Unexpected server error.", "detail": str(exc)}), 500


@app.post("/cj-appointment-conversion")
def cj_appointment_conversion():
    """
    Accept the appointment payload from the client HTML and forward to CJ.

    Expected JSON body (mirrors what conversion-client-afspraak.html sends,
    no "items"):
    {
        "orderId":   "AFS-001",
        "eventTime": "2026-06-14T13:00:00.000Z",
        "amount":    0,
        "currency":  "EUR",
        "cjEvent":   "<cje cookie value>"
    }
    """
    order = request.get_json(silent=True)

    if not order:
        logger.warning("Received request with no JSON body.")
        return jsonify({"error": "Request body must be JSON."}), 400

    required = ("orderId", "eventTime", "currency", "cjEvent")
    missing = [f for f in required if not order.get(f)]
    if order.get("amount") is None:
        missing.append("amount")
    if missing:
        logger.warning("Missing required fields: %s", missing)
        return jsonify({"error": "Missing required fields.", "fields": missing}), 400

    demo = bool(order.pop("demo", False))
    order.pop("affiliateName", None)   # niet doorgeven aan CJ

    endpoint = CJ_ENDPOINT_TEST if demo else CJ_ENDPOINT_LIVE
    logger.info("demo=%s → endpoint: %s", demo, endpoint)

    try:
        result = send_appointment_conversion(order, endpoint=endpoint)
        logger.info("Afspraak-conversie forwarded to CJ. orderId=%s", order.get("orderId"))
        return jsonify(result), 200

    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        return jsonify({"error": "Server configuration error.", "detail": str(exc)}), 500

    except RuntimeError as exc:
        # CJ returned order-level errors (e.g. duplicate orderId)
        logger.error("CJ rejected the order: %s", exc)
        return jsonify({"error": "CJ rejected the conversion.", "detail": str(exc)}), 422

    except Exception as exc:
        logger.exception("Unexpected error forwarding conversion to CJ.")
        return jsonify({"error": "Unexpected server error.", "detail": str(exc)}), 500


if __name__ == "__main__":
    # Development server – do not use in production (use gunicorn / uwsgi instead)
    app.run(host="0.0.0.0", port=8080, debug=True)
