import base64
import json
import os
from typing import List

from openai import OpenAI

import tools as invoice_tools
from models import ExtractedInvoice

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

_EXTRACT_SYSTEM = """
Extract all line items from this invoice.
Return the vendor name and every line item with description, quantity, unit price, and subtotal.
"""  # noqa: E501

_CLASSIFY_SYSTEM = """
You are a tax classification agent for RetailCo.
Call get_tax_categories to see available categories, classify each line item,
compute tax amounts (tax_amount = subtotal * tax_rate),
then call save_invoice_result with the complete result.
"""

_TOOLS: List[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_tax_categories",
            "description": "Fetch all available tax categories and their rates from the database.",  # noqa: E501
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_invoice_result",
            "description": "Save the fully classified invoice result. Call once every line item is classified.",  # noqa: E501
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_id": {"type": "string"},
                    "line_items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "description": {"type": "string"},
                                "quantity": {"type": "number"},
                                "unit_price": {"type": "number"},
                                "subtotal": {"type": "number"},
                                "tax_category": {"type": "string"},
                                "tax_rate": {"type": "number"},
                                "tax_amount": {"type": "number"},
                            },
                            "required": [
                                "description",
                                "quantity",
                                "unit_price",
                                "subtotal",
                                "tax_category",
                                "tax_rate",
                                "tax_amount",
                            ],
                        },
                    },
                    "subtotal": {"type": "number"},
                    "total_tax": {"type": "number"},
                    "total": {"type": "number"},
                },
                "required": [
                    "invoice_id",
                    "line_items",
                    "subtotal",
                    "total_tax",
                    "total",
                ],
            },
        },
    },
]


def _dispatch(tool_name: str, args: dict, invoice_id: str) -> str:
    if tool_name == "get_tax_categories":
        return json.dumps(invoice_tools.get_tax_categories())
    if tool_name == "save_invoice_result":
        # always enforce the correct invoice id regardless of what model passes
        args["invoice_id"] = invoice_id
        return json.dumps(invoice_tools.save_invoice_result(**args))
    return json.dumps({"error": f"unknown tool: {tool_name}"})


def _extract(file_bytes: bytes, content_type: str) -> ExtractedInvoice:
    is_binary = content_type.startswith("image/") or content_type == "application/pdf"

    if is_binary:
        b64 = base64.b64encode(file_bytes).decode()
        user_content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:{content_type};base64,{b64}"},
            }
        ]
    else:
        user_content = [
            {"type": "text", "text": file_bytes.decode("utf-8", errors="replace")}
        ]

    response = client.beta.chat.completions.parse(
        model="gpt-5",
        messages=[
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        response_format=ExtractedInvoice,
    )
    return response.choices[0].message.parsed


def run(invoice_id: str, file_bytes: bytes, content_type: str) -> None:
    extracted = _extract(file_bytes, content_type)

    messages = [
        {"role": "system", "content": _CLASSIFY_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Invoice ID: {invoice_id}\n\n"
                f"Extracted line items:\n{extracted.model_dump_json(indent=2)}"
            ),
        },
    ]

    while True:
        response = client.chat.completions.create(
            model="gpt-5",
            messages=messages,
            tools=_TOOLS,
            tool_choice="auto",
        )

        choice = response.choices[0]

        if choice.finish_reason == "stop":
            break

        messages.append(choice.message.model_dump(exclude_none=True))

        for tool_call in choice.message.tool_calls or []:
            args = json.loads(tool_call.function.arguments)
            result = _dispatch(tool_call.function.name, args, invoice_id)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )
