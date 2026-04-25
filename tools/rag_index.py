"""
RAG index over raw_data — lets agents issue targeted retrieval queries
instead of receiving the full data dump in the context window.

Each raw_data section becomes one or more labeled chunks. Retrieval uses
keyword overlap scoring (no embedding API calls, no extra cost). When ADV
Part 2 brochure text becomes available it can be added via add_brochure_chunks().

Upgrade path: replace search() with OpenAI text-embedding-3-small cosine
similarity once brochure text is indexed — the interface stays identical.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    source: str        # e.g. "registration", "13f_portfolio", "fund:FundName"
    label: str         # human-readable description for the agent
    content: str       # serialized JSON or plain text
    keywords: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self):
        self.keywords = _tokenize(self.content + " " + self.label)


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r'\b[a-z]\w*\b', text.lower()))


def _serialize(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str) if not isinstance(obj, str) else obj


class RawDataIndex:
    """Keyword-searchable index over a single pipeline run's raw_data."""

    def __init__(self, raw_data: dict):
        self._chunks: list[Chunk] = []
        self._build(raw_data)

    # ── Public interface ──────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 4) -> list[dict]:
        """Return the top_k most relevant chunks for query."""
        q = _tokenize(query)
        if not q:
            return [_as_result(c) for c in self._chunks[:top_k]]

        scored: list[tuple[float, Chunk]] = []
        for chunk in self._chunks:
            overlap = len(q & chunk.keywords)
            if overlap == 0:
                continue
            # Boost source/label exact-word matches (e.g. query "13f" boosts 13f_portfolio)
            source_boost = sum(2 for w in q if w in chunk.source.lower())
            phrase_boost = 3 if any(w in chunk.content.lower() for w in query.lower().split()) else 0
            scored.append((overlap + source_boost + phrase_boost, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [_as_result(c) for _, c in scored[:top_k]]

    def available_sources(self) -> list[str]:
        return [c.source for c in self._chunks]

    def add_brochure_chunks(self, chunks: list[dict]) -> None:
        """Extend index with ADV Part 2 brochure sections once text is available."""
        for c in chunks:
            self._chunks.append(Chunk(
                source=c.get("source", "brochure"),
                label=c.get("label", "ADV brochure section"),
                content=c.get("content", ""),
            ))

    # ── Builder ───────────────────────────────────────────────────────────────

    def _add(self, source: str, label: str, obj: Any) -> None:
        if obj is None:
            return
        if isinstance(obj, (dict, list)) and not obj:
            return
        self._chunks.append(Chunk(source=source, label=label, content=_serialize(obj)))

    def _build(self, raw_data: dict) -> None:
        adv = raw_data.get("adv_summary") or {}
        adv_xml = raw_data.get("adv_xml_data") or {}

        # Registration and identity
        self._add("registration", "Firm registration, AUM, employees, clients, firm type",
                  {k: adv.get(k) for k in (
                      "firm_name", "crd", "sec_number", "registration_status",
                      "registration_date", "firm_type", "aum_regulatory",
                      "num_clients", "num_employees", "num_investment_advisers",
                      "headquarters", "website",
                  )})

        # Key personnel and ownership
        self._add("personnel", "Key principals, ownership percentages, titles",
                  adv.get("key_personnel"))

        # Fee structure
        self._add("fees", "Fee types, minimum account size, compensation",
                  adv.get("fee_structure") or adv.get("fees"))

        # Regulatory disclosures
        self._add("regulatory_disclosures",
                  "IAPD disclosure flags, violation types, disciplinary history",
                  adv.get("disclosures") or adv_xml.get("disclosures"))

        # 13F portfolio (most recent)
        thirteenf = adv_xml.get("thirteenf") or {}
        if thirteenf:
            self._add("13f_portfolio",
                      "13F portfolio value, holdings count, top holdings, CIK",
                      thirteenf)

        # 13F history (quarterly AUM trend)
        history = adv_xml.get("thirteenf_history")
        if isinstance(history, list) and history:
            self._add("13f_history",
                      "Quarterly 13F portfolio value history, QoQ changes",
                      history[:5])

        # 13F filing list (dates and accession numbers)
        if raw_data.get("filings_13f"):
            self._add("13f_filings_list",
                      "List of 13F-HR filings with dates and accession numbers",
                      raw_data["filings_13f"][:4])

        # Form D funds — one chunk per fund for targeted retrieval
        fund_disc = raw_data.get("fund_discovery") or {}
        for fund in (fund_disc.get("funds") or [])[:8]:
            name = fund.get("fund_name") or fund.get("name") or "Unknown"
            self._add(f"fund:{name[:40]}",
                      f"Form D fund: {name[:40]} — exemptions, offering, dates",
                      {k: fund.get(k) for k in (
                          "fund_name", "name", "entity_type", "offering_amount",
                          "date_of_first_sale", "jurisdiction", "exemptions",
                          "is_private_fund", "relying_advisors", "news",
                      ) if fund.get(k) is not None})

        # Fund discovery summary (total counts, sources)
        fund_summary = {k: v for k, v in fund_disc.items() if k != "funds"}
        if fund_summary:
            self._add("fund_discovery_summary",
                      "Total funds found, discovery sources, relying advisors count",
                      fund_summary)

        # Enforcement actions
        enforcement = raw_data.get("enforcement") or {}
        if enforcement:
            self._add("enforcement",
                      "SEC/FINRA enforcement actions, penalties, settlement dates",
                      enforcement)

        # ADV brochure metadata (the PDF itself is not yet fetched)
        brochure = adv_xml.get("brochure") or adv.get("brochure")
        if brochure:
            self._add("brochure_metadata",
                      "ADV Part 2A brochure name, date, version — text not yet indexed",
                      brochure)

        # Market context (FRED macro)
        if raw_data.get("market_context"):
            self._add("market_context",
                      "FRED macro: fed funds rate, HY spread, 10Y yield, VIX",
                      raw_data["market_context"])

        # Reconciliation results (if run before analysis)
        if raw_data.get("reconciliation"):
            self._add("reconciliation",
                      "Cross-source reconciliation results: AUM vs 13F, fund counts",
                      raw_data["reconciliation"])


def _as_result(chunk: Chunk) -> dict:
    return {"source": chunk.source, "label": chunk.label, "content": chunk.content}
