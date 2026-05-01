import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import List

import boto3
from boto3.dynamodb.conditions import Key

from models import ClassifiedLineItemInput, SaveResult, TaxCategory

TABLE_NAME = os.environ["TABLE_NAME"]

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def _to_decimal(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, list):
        return [_to_decimal(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_decimal(v) for k, v in obj.items()}
    return obj


def get_tax_categories() -> List[TaxCategory]:
    resp = table.query(KeyConditionExpression=Key("pk").eq("TAXCAT"))
    return [
        TaxCategory(
            id=item["sk"].removeprefix("CAT#"),
            name=item["name"],
            rate=item["rate"],
            description=item.get("description"),
        )
        for item in resp.get("Items", [])
    ]


def _is_excluded(item: ClassifiedLineItemInput) -> bool:
    return (
        item.tax_category == "unclassified"
        or item.quantity is None
        or item.unit_price is None
        or item.subtotal is None
    )


def save_invoice_result(
    invoice_id: str,
    line_items: List[ClassifiedLineItemInput],
) -> SaveResult:
    pk = f"INVOICE#{invoice_id}"
    now = datetime.now(timezone.utc).isoformat()

    items_with_flag = [
        {**item.model_dump(), "excluded": _is_excluded(item)} for item in line_items
    ]

    valid = [item for item in line_items if not _is_excluded(item)]
    subtotal = sum(item.subtotal for item in valid)
    total_tax = sum(item.tax_amount for item in valid)
    total = subtotal + total_tax

    table.put_item(
        Item={
            "pk": pk,
            "sk": "RESULT",
            "line_items": _to_decimal(items_with_flag),
            "subtotal": Decimal(str(subtotal)),
            "total_tax": Decimal(str(total_tax)),
            "total": Decimal(str(total)),
        }
    )

    status = "partial" if len(valid) < len(line_items) else "complete"

    table.update_item(
        Key={"pk": pk, "sk": "METADATA"},
        UpdateExpression="SET #s = :s, updated_at = :t",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status, ":t": now},
    )

    return SaveResult(saved=True, invoice_id=invoice_id, status=status)
