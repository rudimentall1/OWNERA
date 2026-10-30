# OWNERA Resource Intelligence — Market Research

**Status:** Research baseline, not a validated business or implemented capability  
**Research date:** 2026-10-30  
**Owner:** OWNERA  
**Working name:** Resource Intelligence (RI)  
**Related architecture:** [Resource Autonomy](RESOURCE-AUTONOMY.md)

## 1. Executive conclusion

There is a real market for finding and recovering unclaimed financial assets. It is not an empty market and it is not a new discovery. Established specialists already operate in corporate unclaimed-property recovery, probate genealogy, missing-beneficiary tracing, shareholder asset reunification, pension tracing, and blockchain intelligence.

The strongest direct competitor identified in this first pass is **AssetFynd**. It publicly describes an AI-powered global platform, claims matching across 400 million records and 500+ sources in 200+ countries, perpetual alerts, corporate and institutional customers, white-label partnerships, and success-based fees. These are vendor claims, not independently audited performance figures. OWNERA must not position itself as “the first AI to find forgotten money” or assume that stitching public databases together is a defensible moat.

The opportunity worth investigating is narrower:

> Build an agent-assisted investigation and case-orchestration layer that helps a defined professional customer discover, verify, document, prioritize, and lawfully pursue assets across fragmented sources, with transparent evidence and a human/legal approval boundary.

A credible first wedge may be **corporate asset discovery for insolvency practitioners, accountants, law firms, M&A advisers, and multi-entity businesses**, rather than attempting to locate unknown deceased individuals' personal assets worldwide. The first product should be a research and evidence workflow, not a system that claims, transfers, or controls assets.

**Current decision: continue discovery; do not start implementation yet.** The next step is customer and source validation in one jurisdiction and one asset class.

## 2. Definitions and critical distinction

Use these terms precisely:

- **Unclaimed property / unclaimed assets:** money or property owed to an identifiable owner or lawful successor but not collected.
- **Dormant asset:** an asset meeting a jurisdiction- or provider-specific inactivity definition. Dormancy does not itself extinguish ownership.
- **Missing owner / missing beneficiary:** the owner or beneficiary exists but cannot currently be located or connected to the asset.
- **Ownerless property / bona vacantia / escheat:** a legal category whose treatment depends on jurisdiction. It must not be inferred from inactivity.
- **Lost digital asset:** an asset for which credentials, records, keys, or knowledge may be missing. A visible blockchain balance is not proof that the asset is abandoned or ownerless.
- **Dormant organization / DAO:** low governance or operational activity. This does not make its treasury free to use.

A deceased owner with no known heirs is not automatically an ownerless asset. Succession law, escheat, state custody, trusts, creditors, corporate law, limitation periods, and the terms of the relevant instrument all matter.

## 3. Competitor and ecosystem map

This is a first-pass map based on public product descriptions. It is not a complete market census, and vendor claims require diligence.

### 3.1 Direct asset-recovery and corporate unclaimed-property specialists

| Organization | Segment / public proposition | What it means for OWNERA |
|---|---|---|
| [AssetFynd](https://www.assetfynd.com/) | AI-powered global corporate financial asset discovery and recovery. Claims 400m records, 500+ sources, 200+ countries, perpetual alerts, white-label channel and success-based pricing. | Strongest direct benchmark. Any proposed differentiation must be tested against its actual coverage, matching quality, workflows, pricing and customer traction. |
| [Ryan](https://www.ryan.com/practice-areas/abandoned-and-unclaimed-property/) | Corporate abandoned/unclaimed-property compliance and asset recovery; describes searches across 2,000+ repositories, claim preparation and performance-based fees. | Established service-plus-expertise model. Compete on a focused workflow or become a technology partner, not on generic “we search more records.” |
| [Kelmar Associates](https://www.kelmarassoc.com/unclaimed-property-solutions) | Unclaimed-property administration software, claims processing, call centers, holder reporting, securities reconciliation and government-program support. | Strong incumbent in administration and program operations. Shows that claims handling and institutional workflow matter as much as discovery. |
| [DuCharme, McMillen & Associates (DMA)](https://www.dmainc.com/) | Corporate unclaimed-property compliance, reporting, audit support and recovery ecosystem. | Another established specialist; investigate its software, customer base and service boundaries in follow-up research. |
| [MarketSphere](https://www.marketsphere.com/) | Listed by UPPO as a corporate unclaimed-property recovery provider, including contingency-based search and recovery. | Confirms a mature professional-services category, not an empty niche. |
| [Boomerang Asset Recovery](https://www.boomerang-ar.com/) | Corporate asset recovery specialist, listed in UPPO provider directory. | Specialist competitor; validate service scope and geographic coverage directly. |
| [UPPO provider directory](https://www.uppo.org/page/PDAssetRecovery) | Industry directory listing corporate asset recovery providers and due-diligence guidance. | Useful source for competitor discovery, partner candidates and industry vocabulary. |

### 3.2 Probate, heir tracing and missing-beneficiary specialists

| Organization | Segment / public proposition | What it means for OWNERA |
|---|---|---|
| [Finders International](https://www.findersinternational.com/) | Probate genealogy, missing heirs, unknown beneficiaries, unclaimed estates and property-owner tracing across many jurisdictions. | Human research network and legal/probate relationships are significant assets. AI alone will not replace fieldwork or legal proof. |
| [Fraser & Fraser](https://www.fraserandfraser.co.uk/) | Probate research since 1923; missing heirs, beneficiaries, estates, asset/property management and support for legal/public-sector clients. | Long operating history and trust are competitive advantages. |
| [Anglia Research](https://www.angliaresearch.co.uk/) | Missing beneficiaries, financial asset searches, family-tree verification, property-owner tracing and international research network. | Demonstrates adjacent service lines that can be bundled into casework. |
| [Title Research](https://www.titleresearch.com/) | Probate genealogy and missing-beneficiary research. | Include in deeper competitor review; verify current products and markets before drawing conclusions. |

### 3.3 Asset reunification, public search portals and data infrastructure

| Organization / service | Segment / public proposition | What it means for OWNERA |
|---|---|---|
| [MUFG Corporate Markets — AssetTrace+](https://www.mpms.mufg.com/en/mufg-corporate-markets/uk/platforms/asset-reunification/) | Issuer/registrar-led tracing and reunification of shareholders or legal representatives with unclaimed shares/dividends. | Strong incumbent distribution: it works from company share registers and issuer instructions. Potential partner/customer workflow, not a simple competitor to scrape. |
| [NAUPA / MissingMoney](https://unclaimed.org/search/) | Free US public search across participating state unclaimed-property databases, linking users to official claim processes. | Free public discovery creates a low-price ceiling for simple name searches. Value must come from cross-jurisdiction entity resolution, historical corporate lineage, evidence, monitoring and claim workflow. |
| [USAGov — unclaimed money](https://www.usa.gov/unclaimed-money) | Official guide to multiple federal/state sources, including pensions, wages, tax refunds, securities, bank failures and bankruptcy funds. | Confirms source fragmentation. No single US government-wide database covers all categories. |
| [UK Dormant Assets Scheme](https://www.gov.uk/government/publications/the-dormant-accounts-scheme) | Industry-led, government-backed scheme. Participating institutions can transfer qualifying dormant assets; owners retain reclaim rights. | Dormancy is governed by rules and safeguards. The funds are not open capital for third parties. |
| [UK Pension Tracing Service](https://www.gov.uk/find-pension-contact-details) | Finds contact details for pension schemes when the employer/provider is known; does not reveal whether a person has a pension or its value. | A clear example of a discovery-to-provider handoff rather than direct access to assets. |
| [Association of British Insurers — policy tracing](https://www.abi.org.uk/policy-and-guidance/long-term-savings/keep-track-of-your-pension-and-life-insurance/) | Helps identify the current administrator of old pension, life insurance and endowment policies. | Corporate lineage and provider-change resolution are useful patterns for the product. |

### 3.4 Blockchain and DAO intelligence (adjacent, not asset-recovery permission)

| Organization / service | Segment / public proposition | What it means for OWNERA |
|---|---|---|
| [Chainalysis](https://www.chainalysis.com/blockchain-intelligence/) | Maps real-world entities to on-chain activity using address attribution, analytics and investigator expertise. | On-chain attribution is an established, sophisticated market. OWNERA should not claim it can identify wallet owners from inactivity alone. |
| [Arkham](https://arkm.com/) | Entity/address labels, wallet tracking, transaction tracing, analytics and enterprise case tooling. | Strong adjacent competitor for public-chain asset intelligence. Potential integration/data provider subject to terms. |
| [DAOhaus observatory](https://daohaus.com/en) | Public DAO activity and treasury observatory, including quiet/dormant/inactive classifications; states that data is sourced from Snapshot, DefiLlama and Blockscout and can be delayed or wrong. | Useful discovery signal only. A dormant DAO treasury remains governed by its legal and on-chain authority. |
| [DeepDAO](https://deepdao.io/) | Historical DAO governance and treasury analytics. Its own site says data is no longer updated after 2025-11-24 and is a static snapshot. | Do not treat it as a current source without an alternative freshness check. |

## 4. What the market evidence actually proves

### Confirmed by public sources

1. Unclaimed financial assets exist at material scale, but published totals vary and are often estimates.
2. Data is fragmented by jurisdiction, asset class, holder, issuer, court, agency and provider.
3. Existing companies already combine data search, entity matching, research, claims processing and success-based fees.
4. Public portals make basic searches free in several jurisdictions.
5. Institutional buyers value compliance, claimant authentication, evidence, claims processing, security and ongoing monitoring.
6. In the UK, qualifying dormant assets can move into a regulated scheme while owners retain reclaim rights.
7. In Germany, reporting describes billions in inactive accounts, but there is no universal central registry; banks retain account records. This is a discovery and succession problem, not permission for third parties to use funds.
8. Blockchain analytics can attribute some addresses to known entities, but public address balances do not establish abandonment, legal ownership or a right to move funds.

### Not yet proven

- That there is a commercially underserved global market outside AssetFynd and established incumbents.
- That AI agents can materially outperform experienced recovery researchers on legally valid matches.
- That public datasets can be accessed and reused at scale under acceptable terms.
- That a small startup can obtain sufficient high-quality historical data.
- That customers will pay for software independently of contingency-fee recovery services.
- That an OWNERA product can achieve attractive claim conversion rates or predictable time-to-cash.
- That “lost crypto” is a commercially addressable category without the owner's keys, recovery material or lawful authority.

Do not use vendor-published headline asset totals as OWNERA's addressable market. They may overlap, be stale, include duplicate records, or describe assets that are not legally recoverable by the vendor's customers.

## 5. Market gaps worth testing

These are hypotheses, not established facts.

### H1 — Cross-source corporate identity resolution

A company may appear under former names, subsidiaries, acquired entities, dissolved entities, DBAs, old addresses, registration numbers and spelling variants. AssetFynd explicitly says it addresses historical corporate lineages and misspelled names, so this is not automatically a whitespace. Test whether smaller insolvency/accounting/legal firms lack an affordable workflow for their specific cases.

### H2 — Evidence-first case management

A candidate match is not a recoverable asset. A useful product must show:
- source record and retrieval time;
- exact match fields and confidence rationale;
- contradictory evidence;
- corporate/estate lineage;
- applicable jurisdiction and potential claim route;
- documents still required;
- reviewer and approval history;
- final claim outcome and proof of receipt.

This evidence chain could differentiate a generic AI search tool from a professional casework system, but competitor products must be inspected before claiming uniqueness.

### H3 — Continuous monitoring after the first search

A single search becomes stale as agencies publish new records, companies merge, insolvency cases progress or asset records are updated. Perpetual alerts are already a stated AssetFynd feature. The question is whether a narrowly scoped segment needs more transparent source freshness, configurable triggers, or integration into its existing workflow.

### H4 — Small-firm workflow and affordability

Large providers may focus on large corporate portfolios or institutional programs. Test whether smaller insolvency practitioners, boutique law firms, accountants and business owners have a painful, repetitive workflow that is not well served. Do not assume they are underserved solely because they are smaller.

### H5 — Multi-asset case graph

One case may involve a legal entity, predecessor companies, directors, shareholders, insurers, courts, tax agencies, pensions, domains, IP and public blockchain addresses. A graph can connect evidence without asserting common ownership. This may be a useful investigation workspace.

## 6. Candidate customer segments

| Segment | Pain hypothesis | Buyer | Initial willingness-to-pay test |
|---|---|---|---|
| Insolvency practitioners / liquidators | Need to identify assets across historical entities and jurisdictions before closing an estate. | Partner, case manager | Paid pilot on a fixed number of cases. |
| Accounting and tax advisory firms | Clients may have unclaimed balances, credits, refunds or corporate property; research is fragmented. | Partner / practice lead | Per-entity report or monthly monitoring. |
| Boutique corporate law firms | Need documented asset/ownership research for transactions, estates and disputes. | Partner / associate lead | Per-case research workspace. |
| M&A / private equity operations | Need historical entity and asset checks during diligence or post-acquisition cleanup. | Operating partner / diligence lead | Portfolio scan with evidence pack. |
| Estate administration / probate firms | Need asset discovery and beneficiary/estate research. | Probate partner | Per-estate case fee; regulated legal work remains with qualified professionals. |
| Banks, registrars, insurers and public authorities | Need to reunite assets with owners and process claims at scale. | Procurement / operations leadership | Long enterprise sales cycle; not the first customer. |

## 7. Business models to evaluate

1. **B2B SaaS per case / entity:** subscription or case credits for source searches, entity graphs, evidence packs and monitoring.
2. **Research-as-a-service:** fixed-fee asset discovery report with clear scope and human review.
3. **Partner / white-label platform:** software sold to law, tax, insolvency or recovery firms. AssetFynd already advertises a white-label model, so validate differentiation.
4. **Success-based fee:** percentage of recovered assets. Potentially attractive, but legal, licensing, solicitation, claims-agent, consumer-protection and jurisdiction-specific rules require counsel review before launch.
5. **Hybrid:** small research fee plus optional success-based fee where lawful and contractually clear.

Recommended initial test: fixed-fee B2B research pilot. It avoids depending on a long claim cycle before learning whether the product's discovery is useful. Do not promise recovery or take custody of customer assets.

## 8. Jurisdiction strategy

### United States — strongest initial data-discovery candidate

Reasons:
- State-level unclaimed-property programs and a public directory exist.
- MissingMoney aggregates participating states, but not every federal/state asset category.
- Federal agencies maintain separate sources.
- Corporate entity history and multi-state exposure create a clear matching problem.

Risks:
- State-by-state laws, dormancy periods, evidence requirements and claim procedures differ.
- Public availability does not automatically permit bulk scraping or commercial reuse.
- Claimant representation and contingency-fee rules vary.

Potential first wedge: corporate asset discovery for a verified company and its predecessor/subsidiary names, starting with official state/federal sources and a small, explicitly documented set of jurisdictions.

### United Kingdom — strong structured-source candidate

Reasons:
- Dormant Assets Scheme, probate records, pension tracing and asset-reunification workflows are documented.
- Public-sector and registrar processes offer clear handoff paths.

Risks:
- Dormant scheme funds remain reclaimable by owners.
- Probate and heir research requires accuracy and legal process.
- AssetTrace+ and specialist probate firms are established.

Potential first wedge: workflow/evidence software for professional firms, not a new consumer claim portal.

### Germany — large reported pool, difficult first market

Reasons:
- Public reporting has cited multi-billion-euro estimates for inactive accounts.
- There is no central public registry covering forgotten bank accounts.
- Heirs may not know which banks hold accounts.

Risks:
- Bank confidentiality and data access prevent broad automated searches.
- Succession, privacy, banking and legal-service rules apply.
- No open, universal dataset makes a data-led MVP difficult.

Potential first wedge: authorized estate research for a lawyer/administrator with a named deceased person and documented mandate. Not independent scanning of bank accounts.

### Crypto / DAO — research-only at first

Reasons:
- Public chains provide transparent transaction histories.
- Entity intelligence tools and DAO observatories already exist.

Risks:
- Dormancy does not establish abandonment.
- No private key or authorization means no lawful transfer.
- Lost-key recovery is often impossible.
- DAO treasuries may be controlled by multisigs, governance contracts, foundations or legal entities.
- Token balances may be illiquid, frozen, bridged, spam, or economically worthless.

Potential wedge: asset visibility, risk and governance research for an authorized client, not wallet appropriation or “reclaiming” arbitrary dormant balances.

## 9. OWNERA product concept

### Working name: OWNERA Resource Intelligence

A multi-agent research and case-orchestration layer inside OWNERA's Resource Autonomy Engine.

**Promise:** “Find potential assets. Prove the connection. Show the lawful route. Track the outcome.”

### Core workflow

1. **Case intake:** client identifies itself, target entity/person, jurisdiction, purpose and authority to investigate.
2. **Source discovery:** source registry selects approved official and licensed data sources.
3. **Collection:** connectors retrieve permitted records and preserve timestamps, source URLs, terms and hashes where appropriate.
4. **Entity resolution:** deterministic identifiers first (company registration number, court case, issuer ID); probabilistic name/address matching only as a lead.
5. **Relationship graph:** connect entities, predecessor names, subsidiaries, addresses, officers, instruments and asset records with provenance on every edge.
6. **Candidate scoring:** rank by evidence quality, match strength, likely value range if published, claim route, effort, time, costs and legal uncertainty.
7. **Rights and eligibility review:** flag ownership and authority questions; do not make a legal conclusion without qualified review.
8. **Evidence pack:** create a human-readable report with source excerpts, match rationale, conflicts, missing documents and recommended next steps.
9. **Approval and referral:** client or authorized professional decides whether to contact the holder, file a claim or engage counsel.
10. **Outcome tracking:** record accepted/rejected claim, recovery amount if provided by client, fees, elapsed time and evidence of settlement.

### Agent roles

- Source Scout: discovers and monitors approved data sources.
- Corporate Historian: reconstructs entity names, mergers, subsidiaries and registrations.
- Record Matcher: compares candidate records and explains matches.
- Probate / Legal Research Assistant: retrieves public procedural information, never gives final legal advice.
- Asset Analyst: classifies asset type, restrictions, expiry and likely next step.
- Evidence Auditor: checks source quality, contradiction and chain of evidence.
- Case Manager: maintains tasks, deadlines and communications.
- Human Reviewer: approves any externally consequential conclusion or claim.
- Finance Agent: tracks service fees and verified revenue, not hypothetical asset value.

Agents are research workers, not asset custodians, claimants, lawyers, bank operators or signers.

## 10. MVP proposal — research prototype, not financial execution

### Narrow scope

- One jurisdiction: initially evaluate a US state subset or a UK professional workflow.
- One customer type: insolvency/accounting/legal professional.
- One asset category: corporate unclaimed property or court-held funds.
- One input: a client-provided company identity and explicit authorization.
- One output: evidence-backed candidate report and claim-route checklist.

### MVP capabilities

1. Source catalog with official URL, jurisdiction, asset class, access method, update cadence, terms and known limits.
2. Manual upload / structured company identity intake.
3. Search connectors for a small number of official sources.
4. Entity aliases and historical-name records.
5. Candidate match explanation and confidence components.
6. Evidence snapshots with provenance.
7. Human review queue and case status.
8. Exportable report.
9. No claim submission, no custody, no bank access, no wallet signing, no borrowing, no automated outreach in MVP.

### Success criteria

- At least 3 design partners agree to evaluate the workflow.
- At least 10 real, authorized test cases are provided or constructed from public historical records.
- Every candidate result is traceable to a source and retrieval time.
- Human reviewers can distinguish true matches, false positives and unresolved cases.
- Time to produce an evidence pack is measurably lower than the customer's current process.
- At least one customer agrees to a paid pilot.
- No false “verified ownership” claim is made by the system.

If these conditions are not met, change the segment or stop. Do not build a global platform before validating the narrow workflow.

## 11. Defensibility: what could become a moat

Not “we use AI.” AI models and public search interfaces are easy to copy.

Potential compounding advantages:
- legally reusable, high-quality source connectors with source freshness monitoring;
- normalized historical entity and corporate lineage graph;
- case outcomes and reviewer-confirmed match labels, collected with proper rights and consent;
- evidence provenance and audit trail trusted by professional users;
- workflow integrations with case-management, insolvency, accounting and legal systems;
- distribution partnerships with practitioners and recovery firms;
- jurisdiction-specific operational knowledge and documented claim procedures.

Data rights, privacy, security and customer confidentiality are prerequisites. Do not build a moat from scraped personal data of unclear provenance.

## 12. Key risks and kill criteria

| Risk | Why it matters | Mitigation / kill criterion |
|---|---|---|
| Strong incumbent coverage | AssetFynd and established specialists already offer global discovery/recovery. | Inspect real workflows and win a narrowly defined segment. Stop if no meaningful gap is found. |
| Low data access | Critical records may be private, paywalled, non-indexed or prohibited for bulk reuse. | Validate source access before product coding. |
| False positives | Wrongly associating an asset with a person/company can cause harm and liability. | Evidence-first matching, conservative thresholds, human review. |
| Legal perimeter | Claims, heir tracing, legal advice, contingency fees and personal data are regulated differently by jurisdiction. | Qualified local counsel before commercial claims activity. |
| Long time to cash | Asset recovery may take months or years. | Start with paid research pilots, not only success fees. |
| Customer acquisition | Large incumbents have trust and institutional relationships. | Sell to a narrow practitioner segment through direct interviews and pilots. |
| Privacy/security | Cases may contain financial, identity and family data. | Data minimization, purpose limitation, access controls, retention schedule, encryption, audit. |
| Crypto misinterpretation | Dormant wallet is not proof of lost or abandoned ownership. | Read-only intelligence only; no key discovery, unauthorized access or transfer. |
| Overbuilding | Global coverage is expensive and distracts from near-term income. | One jurisdiction, one segment, one asset class; stop if paid demand is absent. |

## 13. Research backlog

Priority order:

1. **AssetFynd teardown:** request demo or collect detailed product evidence; map coverage, supported jurisdictions, entity resolution, source refresh, workflow, API, pricing, customer references, limitations and integrations.
2. **Customer interviews:** 5 insolvency practitioners, 5 accountants/tax advisers, 5 boutique law firms or M&A operators. Ask about last real case, current tools, hours spent, recovered value, false positives, procurement and budget.
3. **US source feasibility:** choose 3 states and 2 federal repositories; document API/bulk access, terms, identifiers, refresh cadence and claim process.
4. **UK source feasibility:** probate, Companies House, dormant assets, pension and registrar sources; document permitted use and handoff.
5. **Germany legal/source memo:** no central bank-account registry; map authorized estate workflows, probate/public notices and legal access restrictions with local counsel.
6. **Competitive interviews:** AssetFynd, Ryan, Kelmar, DMA, one probate research firm and one registrar/asset reunification provider.
7. **Unit economics:** researcher time per case, cost per source, match precision, paid pilot price, recovery cycle and gross margin.
8. **Data protection review:** GDPR, US state privacy requirements, purpose limitation, lawful basis, retention, data subject rights and cross-border transfers.
9. **Partner strategy:** identify law firms, insolvency practices, accountants and recovery specialists who can legally perform claims.
10. **Decision memo:** choose build, partner, niche, or no-go based on evidence.

## 14. Source register

Primary/public sources used for this baseline (accessed 2026-10-30):

1. AssetFynd product and claims: https://www.assetfynd.com/
2. AssetFynd about and model: https://www.assetfynd.com/about
3. UPPO corporate asset recovery provider directory: https://www.uppo.org/page/PDAssetRecovery
4. UPPO pre-escheat owner location directory: https://www.uppo.org/page/PDPreEscheat
5. Ryan abandoned/unclaimed property services: https://www.ryan.com/practice-areas/abandoned-and-unclaimed-property/
6. Kelmar unclaimed property solutions: https://www.kelmarassoc.com/unclaimed-property-solutions
7. Kelmar process and claims support: https://www.kelmarassoc.com/unclaimed-property-solutions/process-and-support
8. Fraser & Fraser services: https://www.fraserandfraser.co.uk/about-us/what-we-do/
9. Finders International: https://www.findersinternational.com/
10. Anglia Research services: https://www.angliaresearch.co.uk/services/
11. MUFG Asset Reunification: https://www.mpms.mufg.com/en/mufg-corporate-markets/uk/platforms/asset-reunification/
12. NAUPA search: https://unclaimed.org/search/
13. USAGov unclaimed money: https://www.usa.gov/unclaimed-money
14. US Treasury unclaimed assets: https://fiscal.treasury.gov/about-us/unclaimed-assets
15. UK Dormant Assets Scheme: https://www.gov.uk/government/publications/the-dormant-accounts-scheme
16. UK Pension Tracing Service: https://www.gov.uk/find-pension-contact-details
17. ABI pension and life insurance tracing: https://www.abi.org.uk/policy-and-guidance/long-term-savings/keep-track-of-your-pension-and-life-insurance/
18. German Banks Association, accounts after death: https://bankenverband.de/en/consumers/case-death-dealing-bank-accounts
19. Finanztip, forgotten accounts in Germany: https://www.finanztip.de/daily/so-findest-du-vergessene-konten-von-angehoerigen/
20. DW, forgotten German bank accounts (2 June 2026): https://amp.dw.com/de/wem-geh%C3%B6ren-die-milliarden-auf-vergessenen-bankkonten/a-77388000
21. Chainalysis blockchain intelligence: https://www.chainalysis.com/blockchain-intelligence/
22. Arkham: https://arkm.com/
23. DAOhaus observatory: https://daohaus.com/en
24. DeepDAO (site states static snapshot, last updated 2025-11-24): https://deepdao.io/

## 15. Strategic decision record

- **Keep as a research direction under OWNERA Resource Autonomy.**
- **Do not create a separate repository yet.**
- **Do not claim that OWNERA can access or appropriate ownerless assets.**
- **Do not make dormant wallets or inactive DAOs a revenue assumption.**
- **Do not build a global scraper or claim-submission bot before source and legal validation.**
- **Prioritize commercial agent / agent workforce for near-term earned revenue.** Resource Intelligence is a later business line unless customer discovery reveals a faster paid pilot.
- **Next gate:** obtain evidence from customer interviews and a source-access matrix; then make a go/no-go decision for a narrow prototype.

The objective is not to “take forgotten money.” It is to find assets and rights that a verified client is legally entitled to recover, or resources that a provider is authorized to license, sell, grant or allocate. OWNERA earns by delivering a verifiable service.
