from flask import Flask, request, Blueprint
import json
import logging
from webhook_service import push_to_all_users

alert_bp = Blueprint("alert_bp", __name__)
logging.basicConfig(filename="error.log", level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")

@alert_bp.route('/alert', methods=['POST'])
def alertmanager_webhook():
    try:
        data = request.get_json(force=True)
        logging.error(f"[Webhook] Received alert: {json.dumps(data, indent=2, ensure_ascii=False)}")

        alerts = data.get("alerts", [])
        for alert in alerts:
            message = alert.get("annotations", {}).get("description", "收到警報")
            logging.error(f"[Webhook] Will push message: {message}")
            push_to_all_users(message=message)
        return "ok"
    except Exception as e:
        logging.exception("Webhook error:")
        return "error", 500
