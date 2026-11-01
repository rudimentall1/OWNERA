"""Deterministic, non-executing plans for supported NEAR research assignments.

Marketplace text is untrusted. This module matches only known task families and
returns a research outline; it never turns buyer text into shell commands, URLs,
credentials, or marketplace actions.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResearchTemplate:
    key: str
    title_markers: tuple[str, ...]
    research_question: str
    source_urls: tuple[str, ...]
    sections: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    min_words: int
    max_words: int


COMMON_CRITERIA = (
    "Every factual claim must cite a source URL actually opened during execution.",
    "Separate measured facts, self-reported figures, estimates, and unknowns.",
    "Show calculation methods and assumptions for every estimate.",
    "Use primary sources first and identify evidence gaps explicitly.",
    "Deliver English Markdown with a concise answer before supporting evidence.",
)

TEMPLATES: tuple[ResearchTemplate, ...] = (
    ResearchTemplate(
        key="agent_to_agent_commerce",
        title_markers=("where agent-to-agent commerce already has volume",),
        research_question="Which agent-to-agent marketplaces, protocols, and payment rails move verifiable volume today, and what mechanics drive it?",
        source_urls=(
            "https://docs.cdp.coinbase.com/x402/welcome",
            "https://docs.virtuals.io/",
            "https://olas.network/",
            "https://docs.fetch.ai/",
            "https://google.github.io/A2A/",
            "https://docs.market.near.ai/",
            "https://modelcontextprotocol.io/",
        ),
        sections=("Executive answer", "Comparison of marketplaces and protocols", "Volume and pricing evidence", "Discovery and payment mechanics", "Common traits of high-volume systems", "What Agent Market should do next"),
        acceptance_criteria=COMMON_CRITERIA + (
            "Cover x402, Virtuals ACP, Olas, Fetch.ai Agentverse, Google A2A, paid MCP tools, and per-call agent marketplaces.",
            "For each system address traded service, buyer type, volume, price, discovery, payment, account requirements, and fees.",
            "Rank no more than five concrete recommendations for Agent Market.",
        ),
        min_words=1000, max_words=2500,
    ),
    ResearchTemplate(
        key="recurring_outsourced_tasks",
        title_markers=("what tasks agents outsource repeatedly",),
        research_question="Which recurring tasks do agents already outsource to external services, and which are suitable for agent-to-agent marketplace jobs?",
        source_urls=(
            "https://www.zyte.com/pricing/",
            "https://www.twilio.com/en-us/pricing",
            "https://replicate.com/pricing",
            "https://modal.com/pricing",
            "https://openrouter.ai/pricing",
            "https://www.deepl.com/pro-api",
            "https://www.upwork.com/resources/how-much-does-upwork-cost",
            "https://www.fiverr.com/support/articles/360010451217-Service-fees",
            "https://docs.market.near.ai/",
        ),
        sections=("Executive answer", "Evidence and method", "Ranked task-family table", "Price and latency benchmarks", "Best five tasks for Agent Market", "What Agent Market should do next"),
        acceptance_criteria=COMMON_CRITERIA + (
            "Rank 15 to 20 task families by expected volume and suitability for agent-to-agent delivery.",
            "For each family state unit price, acceptable latency, automatic verifiability, and public volume signals.",
            "Identify five task families Agent Market should seed first and explain why.",
        ),
        min_words=1000, max_words=2500,
    ),
    ResearchTemplate(
        key="specialist_agent_integrations",
        title_markers=("how hire a specialist agent becomes a tool",),
        research_question="What is the shortest practical path to let an agent framework delegate a task to a marketplace specialist?",
        source_urls=(
            "https://openai.github.io/openai-agents-python/",
            "https://platform.claude.com/docs/en/agent-sdk/overview",
            "https://docs.langchain.com/oss/python/langgraph/overview",
            "https://docs.crewai.com/",
            "https://microsoft.github.io/autogen/stable/",
            "https://google.github.io/adk-docs/",
            "https://ai-sdk.dev/docs/introduction",
            "https://docs.n8n.io/",
            "https://modelcontextprotocol.io/",
        ),
        sections=("Executive answer", "Framework comparison", "Integration friction and payment", "Three integration specifications", "Long-running task result handling", "What Agent Market should do next"),
        acceptance_criteria=COMMON_CRITERIA + (
            "Cover OpenAI Agents SDK, Claude Agent SDK, LangGraph, CrewAI, AutoGen, Google ADK, Vercel AI SDK, n8n, Zapier, and Make.",
            "Compare installation, remote MCP/OAuth, secrets and payment configuration, discovery, ecosystem size, and an adopted paid tool example.",
            "Specify three integrations including tool name, arguments, configuration, result handling, and payment flow.",
        ),
        min_words=1000, max_words=2500,
    ),
    ResearchTemplate(
        key="distribution_channels",
        title_markers=("where agents and their developers find tools", "distribution channels"),
        research_question="Which directories, registries, catalogs, and discovery channels drive installs for agent tools, and what does listing require?",
        source_urls=(
            "https://registry.modelcontextprotocol.io/",
            "https://smithery.ai/",
            "https://glama.ai/mcp/servers",
            "https://www.pulsemcp.com/",
            "https://mcp.so/",
            "https://developers.openai.com/apps-sdk/",
            "https://docs.anthropic.com/en/docs/claude-code/mcp",
            "https://docs.cdp.coinbase.com/x402/welcome",
            "https://google.github.io/A2A/",
            "https://huggingface.co/",
            "https://www.npmjs.com/",
            "https://pypi.org/",
        ),
        sections=("Executive answer", "Channel comparison", "Listing eligibility and review", "Traffic and install evidence", "Ranked top-five submission plan", "What Agent Market should do next"),
        acceptance_criteria=COMMON_CRITERIA + (
            "Cover official MCP Registry, Smithery, Glama, PulseMCP, mcp.so, Claude connectors, ChatGPT apps, x402 catalogs, A2A directories, GitHub, Hugging Face, npm, and PyPI.",
            "For each channel address submission, review, traffic evidence, cost, and Agent Market eligibility.",
            "Rank channels by expected installs per month per hour of effort and give exact steps for the top five.",
        ),
        min_words=1000, max_words=2500,
    ),
    ResearchTemplate(
        key="completed_jobs_metrics",
        title_markers=("defining and instrumenting completed jobs per day",),
        research_question="How should Agent Market define, measure, and decompose completed jobs per day so the metric reflects organic value?",
        source_urls=(
            "https://docs.market.near.ai/",
            "https://stripe.com/docs/connect",
            "https://investors.etsy.com/financials/quarterly-results/default.aspx",
            "https://investors.upwork.com/financials/quarterly-results/default.aspx",
            "https://investors.airbnb.com/financials/quarterly-results/default.aspx",
            "https://amplitude.com/blog/north-star-metric",
            "https://mixpanel.com/blog/product-metrics/",
        ),
        sections=("Executive answer", "Comparable marketplace definitions", "Recommended metric definition and exclusions", "Funnel and formulas", "One-page dashboard", "Three leading indicators"),
        acceptance_criteria=COMMON_CRITERIA + (
            "Define completed jobs per day with explicit exclusions for self-hires, internal accounts, test traffic, refunds, disputes, retries, multi-slot jobs, and recurring runs.",
            "Provide five to eight funnel stages with formulas and growth-accounting definitions.",
            "Specify a one-page dashboard and three weekly leading indicators.",
        ),
        min_words=1000, max_words=2500,
    ),
    ResearchTemplate(
        key="micro_job_economics",
        title_markers=("economics of micro-jobs on a marketplace",),
        research_question="At what price does the current held-payment and judge model stop working, and what must change for high-volume micro-jobs?",
        source_urls=(
            "https://stripe.com/pricing",
            "https://www.rapidapi.com/pricing",
            "https://www.twilio.com/en-us/pricing",
            "https://replicate.com/pricing",
            "https://modal.com/pricing",
            "https://openrouter.ai/pricing",
            "https://www.upwork.com/resources/how-much-does-upwork-cost",
            "https://www.fiverr.com/support/articles/360010451217-Service-fees",
            "https://docs.cdp.coinbase.com/x402/welcome",
            "https://docs.market.near.ai/",
        ),
        sections=("Executive answer", "Current fee and settlement model", "Cost model by price point", "Break-even threshold", "Ranked model changes", "What Agent Market should do next"),
        acceptance_criteria=COMMON_CRITERIA + (
            "Model $0.05, $0.20, $1, and $5 jobs with platform fee, payment rail, judge, dispute exposure, and support costs.",
            "Show break-even calculations and identify which inputs are measured versus assumed.",
            "Rank fee, batching, settlement, judge, and minimum-price changes with numeric rationale.",
        ),
        min_words=1000, max_words=2500,
    ),
    ResearchTemplate(
        key="agent_directory_lookup",
        title_markers=("find sagekai agent",),
        research_question="Find the exact public SageKai agent profile in NEAR Agent Market, or report not found if no verifiable match exists.",
        source_urls=("https://market.near.ai/agents", "https://docs.market.near.ai/"),
        sections=("Search method", "Exact match and profile URL", "Similar-name disambiguation", "Conclusion"),
        acceptance_criteria=(
            "Search only public agent directory pages and documented public search APIs.",
            "Open and cite the exact profile URL for a positive match.",
            "If no exact public match is verified, state not found without guessing.",
        ),
        min_words=100, max_words=500,
    ),
)


def _canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_assignment_plan(item: dict[str, Any]) -> dict[str, Any] | None:
    """Return a deterministic plan for a supported active assignment, else None.

    The raw marketplace description is fingerprinted but never used as a command,
    URL list, shell fragment, or tool instruction.
    """
    if not isinstance(item, dict):
        raise TypeError("assignment item must be an object")
    assignment = item.get("assignment")
    job = item.get("job")
    if not isinstance(assignment, dict) or not isinstance(job, dict):
        return None
    assignment_id = assignment.get("assignmentId")
    job_id = assignment.get("jobId") or job.get("jobId")
    status = assignment.get("status")
    title = job.get("title")
    description = job.get("description")
    if not all(isinstance(value, str) and value.strip() for value in (assignment_id, job_id, status, title, description)):
        return None
    if status.casefold() not in {"assigned", "accepted", "started", "in_progress"}:
        return None
    if len(title) > 300 or len(description) > 30_000:
        raise ValueError("marketplace job brief exceeds planner limits")

    normalized_title = " ".join(title.casefold().split())
    template = next(
        (candidate for candidate in TEMPLATES if any(marker in normalized_title for marker in candidate.title_markers)),
        None,
    )
    if template is None:
        return None

    brief_digest = hashlib.sha256(description.encode("utf-8")).hexdigest()
    plan_body = {
        "schema": "ownera.near-market-research-plan.v1",
        "assignment_id": assignment_id,
        "job_id": job_id,
        "assignment_status_at_planning": status,
        "plan_key": template.key,
        "title": title,
        "research_question": template.research_question,
        "source_urls_to_open": list(template.source_urls),
        "deliverable_sections": list(template.sections),
        "acceptance_criteria": list(template.acceptance_criteria),
        "word_count": {"minimum": template.min_words, "maximum": template.max_words},
        "brief_sha256": brief_digest,
        "execution_state": "PLAN_READY_NOT_EXECUTABLE",
        "execution_blockers": [
            "No verified source-fetch and citation-capture worker is connected yet.",
            "No independent semantic reviewer is connected yet.",
            "This plan contains no executable command and does not start or submit the assignment.",
        ],
    }
    plan_body["plan_sha256"] = _canonical_digest(plan_body)
    return plan_body
