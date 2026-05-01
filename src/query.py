import json

from repository import repo, to_float


def handle(event):
    invoice_id = (event.get("pathParameters") or {}).get("id")
    if not invoice_id:
        return {"statusCode": 400, "body": json.dumps({"error": "missing invoice id"})}

    try:
        meta = repo.get_metadata(invoice_id)
    except Exception:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "failed to read invoice"}),
        }

    if not meta:
        return {"statusCode": 404, "body": json.dumps({"error": "invoice not found"})}

    status = meta["status"]

    if status == "pending":
        return {
            "statusCode": 200,
            "body": json.dumps({"invoice_id": invoice_id, "status": "pending"}),
        }

    if status == "failed":
        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "invoice_id": invoice_id,
                    "status": "failed",
                    "error": meta.get("error", "processing failed"),
                }
            ),
        }

    try:
        result = repo.get_result(invoice_id)
    except Exception:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "failed to read invoice result"}),
        }

    body = {
        "invoice_id": invoice_id,
        "status": status,
        "line_items": to_float(result.get("line_items", [])),
        "subtotal": to_float(result.get("subtotal")),
        "total_tax": to_float(result.get("total_tax")),
        "total": to_float(result.get("total")),
    }

    if meta.get("vendor"):
        body["vendor"] = meta["vendor"]

    return {"statusCode": 200, "body": json.dumps(body)}
