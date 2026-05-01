import json

import presign
import query
import tax_categories


def lambda_handler(event, context):
    route = event.get("routeKey", "")

    if route == "GET /health":
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "ok"}),
        }

    if route == "POST /invoice":
        return presign.handle(event)

    if route == "GET /invoice/{id}":
        return query.handle(event)

    if route == "POST /tax-categories":
        return tax_categories.handle(event)

    return {"statusCode": 404, "body": json.dumps({"error": "not found"})}
