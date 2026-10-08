"""Shared structured Gemini reviewer for financial-policy claims."""

from __future__ import annotations

from typing import Any, Literal

import instructor
from pydantic import BaseModel, Field


SYSTEM_INSTRUCTION = """You are a financial-policy claim reviewer. Use only the provided
policy and claim facts. Do not assume an organisation, currency, receipt, approval,
business purpose, exchange-rate evidence, or exception that is not stated.

Classify the claim as Compliant when the facts meet the policy; Non-compliant when the
facts clearly violate it; or Needs review when policy-required evidence or a material
fact is missing. Return a concise, audit-ready decision. Cite policy section identifiers
where available. In reasoning_summary, give one to three concise policy-to-fact reasons;
do not provide hidden chain-of-thought."""


class FinancialPolicyDecision(BaseModel):
    """Validated decision returned by Gemini and exposed by the API."""

    classification: Literal["Compliant", "Non-compliant", "Needs review"] = Field(
        description="The policy decision for this claim."
    )
    explanation: str = Field(description="A short, factual explanation of the decision.")
    policy_references: list[str] = Field(
        default_factory=list,
        description="Policy section identifiers that support the decision.",
    )
    reasoning_summary: list[str] = Field(
        min_length=1,
        max_length=3,
        description="One to three concise policy-to-claim facts supporting the decision.",
    )
    evidence_gaps: list[str] = Field(
        default_factory=list,
        description="Missing facts or documents that prevent a definitive decision.",
    )


def create_structured_client(gemini_client: Any) -> Any:
    """Wrap a Google GenAI client with Instructor validation and retries."""
    return instructor.from_genai(gemini_client, mode=instructor.Mode.JSON)


def review_claim(
    client: Any,
    model: str,
    claim: str,
    *,
    claim_id: str | None = None,
    policy_text: str | None = None,
    cached_content: str | None = None,
) -> tuple[FinancialPolicyDecision, Any]:
    """Review one claim using either inline policy text or an explicit Gemini cache."""
    if bool(policy_text) == bool(cached_content):
        raise ValueError("Provide exactly one of policy_text or cached_content.")

    messages: list[dict[str, str]] = []
    if policy_text:
        messages.extend(
            [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": "Financial policy to apply:\n\n" + policy_text},
            ]
        )

    label = f"Claim {claim_id}" if claim_id else "Expense claim"
    messages.append({"role": "user", "content": f"{label}:\n{claim.strip()}\n\nClassify this claim now."})
    request: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "response_model": FinancialPolicyDecision,
        "generation_config": {"temperature": 0},
        "max_retries": 2,
    }
    if cached_content:
        request["cached_content"] = cached_content

    return client.chat.completions.create_with_completion(**request)
