# Discovery and design

## Source and status

This project documents the **synthetic** “澄岳研究院 / 科研采购与供应商交付” case in the [FDE discovery lab](https://fde-discovery-lab-67046.app.workbuddy.host/lab?case=research-procurement). Six roles were interviewed on 2026-10-23. The lab recorded **24/36** interview facts and generated six candidate needs. Interview statements are case evidence, not observed production performance or approved policy. The open questions below must be resolved before a live pilot.

The proposed process is shown in [the flowchart](flowchart.svg). Its colored branches distinguish routine checks, human decisions, and exception handling; it is a pilot design, not an approved operating procedure.

## Confirmed case statements

| Area | Case evidence | ID |
| --- | --- | --- |
| Management goal | Mean procurement duration 18 → 10 days; urgent purchase share 27% → <12%. | f00 |
| Process | Request → inventory check → quotation comparison → approval → receipt; node waiting and processing times are not measured. | f01 |
| Pilot | 20 common reagents over six weeks; specification review accuracy ≥98%; urgent purchase share should fall. | f02 |
| Budget and authority | Initial budget ¥120,000 includes integration, training, validation; maintenance and human review costs must be deducted. Safety officer can veto launch. | f03, f04 |
| Frontline work | Similar specifications and different lead times cause repeated concentration/package confirmation. About 160 requests/month, four rounds/request, 20 minutes/round. | f10, f12 |
| Receipt incident | A refrigerated reagent arrived Friday with nobody available to accept it; the temperature record was missing the next day. | f11 |
| Field constraints | Peak time uses existing terminals; drafts need saving and a visible last sync time. | f13 |
| Procurement records | Workflow steps need inputs, outputs, owner and return reason; source material includes reagent specifications, three quotes, hazardous materials list, and receipt temperature logs. | f20, f21 |
| Procurement authority | Procurement can organize and review, but cannot perform safety sign-off or autonomously select a supplier. | f22 |
| Handoff | Business ID, version, status, unresolved items and receiver are required. Handoff ends only after receiver confirmation. | f23 |
| Systems and identity | Procurement platform, ERP and inventory sheet have separate permissions and no unified state view; CAS, product name and supplier SKU are competing identifiers. | f30, f31 |
| Interface and quality | Procurement/inventory can be read; the tool cannot auto-pay or approve hazardous purchases. Ambiguous records go to a human repair queue and must not enter automatic recommendations. | f32, f33 |
| Safety | Hazard qualification, cold-chain acceptance and budget approval cannot be bypassed; only authorized roles may view source records. | f40, f41 |
| Safety pilot | Stop on a safety condition; evaluation records are provisionally retained 90 days in this simulation, with real retention to be determined by organization policy. | f42, f43 |
| Service | Measure handoff waiting and repeat contact per case; fix denominator, exclusions and period. Complaints link to business ID/version; no unconfirmed compensation or outcome promises. | f51, f53, f54 |

All IDs in this table use the `research-procurement-` prefix. The table groups the 24 recorded statements by subject.

## Candidate needs and priority

| Priority | Hypothesis | Why it is first or later | Pilot evidence to collect |
| --- | --- | --- | --- |
| P0 | Read-only specification checks with human acceptance/rejection | Frequent repeated confirmation; errors can be caught before purchase. | Per-request mismatch category, confirmation rounds, reviewer decision, correct/incorrect result. |
| P0 | Traceable handoff and receipt prompts | An unconfirmed handoff and missing cold-chain record create ownership and safety risk. | Entry/exit/receiver confirmation times, missing temperature logs, reopening count. |
| P0 | Written approval and safety matrix | Safety officer has veto authority; the tool must not cross purchasing or safety boundaries. | Named approvers, prohibited actions, zero unauthorized reads/actions. |
| P1 | CAS/name/SKU crosswalk and state view | Ambiguous identity makes a suggestion unreliable. | Mapping coverage, duplicates, repair queue ownership and age. |
| P1 | Node-level timing | The 18-day baseline cannot be attributed to a step. | Start/end times, exclusion rules, sample window and denominator. |
| P2 | Complaint explanation and feedback loop | Can be investigated separately from purchasing decisions. | Case-linked feedback, repeat contacts and completed handoffs. |

These are **hypotheses**, not validated benefits. The apparent four × 20-minute rounds should not be multiplied into a savings claim until a baseline sample and actual reduction are measured.

## Prototype boundary

The CLI reads local JSON only. It matches CAS plus concentration and package exactly, rejects ambiguous catalog matches, checks source age and missing approvals, and flags unconfirmed handoffs or cold-chain logs. It returns `ready_for_human_review` only when local checks pass. The output always has `approved: false`. No network connection, write-back, supplier ranking, purchase approval, payment or autonomous safety decision is present.

This deliberately small implementation is a rule baseline for measuring whether a later AI suggestion adds value. No model score is used as a safety decision. The 30-day sample catalog age in `config/default.yaml` is a demonstration setting, **not** a policy established by the interviews.

## Pilot measurement and stop conditions

Before the six-week pilot, agree on the 20-reagent list, historical sample window, reviewer names and a fixed denominator. Compare specification accuracy, confirmation rounds, urgent-purchase share and node elapsed time against the baseline. Record missing documents and false suggestions per case. Pause and route to named staff when hazard qualification, budget approval, cold-chain acceptance, role authorization, or source identity is missing or disputed. Safety staff own the launch veto and stop review.

## Open investigation items (12)

1. Management: exact first-scope reagent list and participating research group.
2. Lab assistant: off-system work habits and their causes.
3. Lab assistant: review path for an incorrect suggestion.
4. Procurement: rule owner and conflict resolution.
5. Procurement: incident assignment and escalation.
6. Systems: source refresh frequency and expiration thresholds.
7. Systems: outage and interface failure fallback.
8. Safety: cases requiring manual fallback and receiver.
9. Safety: audit artifacts and change history.
10. Research lead: cross-team handoff conflicts.
11. Research lead: precise automation exclusion scope.
12. Research lead: feedback intake and improvement cadence.

The lab's stage report also calls for original written requirements, comparable industry evidence, real sample records, interface inventory, approval matrix, anomaly frequency, and actual maintenance/review cost. Those sources were not supplied by the simulation.
