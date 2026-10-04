"""OpenCode-compatible LLM client for structured draft generation."""
import json
import logging
from uuid import uuid4

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class DraftContentOutput(BaseModel):
    """Structured output for the vendor onboarding draft node."""

    vendor_summary: str = Field(description="One-paragraph summary of the vendor and proposed engagement.")
    checklist: list[str] = Field(description="Concrete onboarding checklist items grounded in the retrieved sources.")
    risk_indicators: list[str] = Field(description="Specific risk indicators based on intake flags and retrieved sources.")
    missing_information: list[str] = Field(description="Facts that are unknown or unsupported by the retrieved sources.")
    recommended_next_steps: list[str] = Field(description="Actionable next steps for the requester or approver.")


class GenericDraftContentOutput(BaseModel):
    """Structured output for any playbook draft."""

    summary: str = Field(description="One-paragraph summary of the request and context.")
    checklist: list[str] = Field(description="Concrete checklist items grounded in the retrieved sources.")
    risk_indicators: list[str] = Field(description="Specific risk indicators based on intake and retrieved sources.")
    missing_information: list[str] = Field(description="Facts that are unknown or unsupported by the retrieved sources.")
    recommended_next_steps: list[str] = Field(description="Actionable next steps for the requester or approver.")


class LLMError(RuntimeError):
    """Raised when the LLM cannot produce a usable structured response."""


def get_llm() -> ChatOpenAI:
    """Return a configured ChatOpenAI instance for OpenCode."""
    settings = get_settings()
    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY is not configured")
    # OpenCode Go requires a session header for routing.
    return ChatOpenAI(
        model=settings.llm_model,
        temperature=0,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        default_headers={
            "x-opencode-session": str(uuid4()),
            "HTTP-Referer": "https://localhost",
            "X-Title": "Acme Legal Playbook Assistant",
        },
    )


def _format_passages(retrieved_passages: list[dict]) -> str:
    """Format retrieved passages for inclusion in an LLM prompt."""
    return "\n\n---\n\n".join(
        f"Source: {p.get('title', 'Unknown')} v{p.get('version', '?')}"
        f"{f' · {p.get('section')}' if p.get('section') else ''}\n{p.get('content', '')}"
        for p in retrieved_passages
    ) or "No approved source passages were retrieved."


def _clean_json_content(content: str) -> str:
    """Remove markdown fences and JSON labels from model output."""
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()
    return content


async def generate_playbook_draft(
    system_prompt: str,
    request_json: str,
    retrieved_passages: list[dict],
) -> dict:
    """Generate a generic playbook draft using a custom system prompt.

    Uses JSON-object mode if supported; otherwise parses JSON from plain text.
    Returns a dict with summary, checklist, risk_indicators, missing_information,
    and recommended_next_steps.
    """
    passages_text = _format_passages(retrieved_passages)
    human_prompt = (
        "## Intake answers\n"
        f"{request_json}\n\n"
        "## Retrieved approved policy passages\n"
        f"{passages_text}\n\n"
        "## Task\n"
        "Produce a JSON object with exactly these keys:\n"
        "- summary (string)\n"
        "- checklist (list of strings)\n"
        "- risk_indicators (list of strings)\n"
        "- missing_information (list of strings)\n"
        "- recommended_next_steps (list of strings)\n\n"
        "Base every item only on the intake and the retrieved passages."
    )
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]

    try:
        llm = get_llm()
        try:
            json_llm = llm.bind(response_format={"type": "json_object"})
            raw = await json_llm.ainvoke(messages)
        except Exception:
            raw = await llm.ainvoke(messages)

        content = _clean_json_content(str(raw.content))
        data = json.loads(content)
        # Validate structure loosely.
        GenericDraftContentOutput(**data)
        return data
    except Exception as exc:
        logger.warning("LLM draft generation failed (%s)", type(exc).__name__)
        raise LLMError("Could not generate draft with LLM") from exc


async def generate_vendor_onboarding_draft(
    request_json: str,
    retrieved_passages: list[dict],
) -> DraftContentOutput:
    """Generate a cited, structured draft for the legacy vendor onboarding playbook."""
    system_prompt = (
        "You are an AI assistant for Acme Technologies LLC legal operations. "
        "Produce a vendor onboarding checklist and risk summary strictly grounded "
        "in the approved policy passages provided.\n\n"
        "Rules:\n"
        "1. Use only facts that appear in the retrieved source passages.\n"
        "2. If the intake raises a risk but no source passage supports the required action, "
        "   add the item to missing_information instead of inventing a requirement.\n"
        "3. Keep the tone professional and concise.\n"
        "4. The output is a draft for qualified human review, not a final legal determination.\n\n"
        "5. Respond with valid JSON only. Do not include markdown code fences or explanations."
    )
    data = await generate_playbook_draft(system_prompt, request_json, retrieved_passages)
    # Map generic output to legacy vendor onboarding schema.
    return DraftContentOutput(
        vendor_summary=data.get("summary", data.get("vendor_summary", "")),
        checklist=data.get("checklist", []),
        risk_indicators=data.get("risk_indicators", []),
        missing_information=data.get("missing_information", []),
        recommended_next_steps=data.get("recommended_next_steps", []),
    )
