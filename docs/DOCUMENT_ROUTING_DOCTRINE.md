DOCUMENT_ROUTING_DOCTRINE.md 03.12.2026
Purpose: define where documents belong so internal records, engineering truth, public docs, and working notes never get mixed again

────────────────────────────────

SECTION 1 - CORE RULE

Before saving any document, first classify it.

Every document must be assigned exactly one of these classes:
 1. INTERNAL_OPERATIONAL_RECORD
 2. CANONICAL_ENGINEERING_DOC
 3. PRODUCT_DOCUMENTATION
 4. WORKING_NOTE

Do not save first and classify later.

────────────────────────────────

SECTION 2 - DOCUMENT CLASSES

INTERNAL_OPERATIONAL_RECORD

Used for:
status reports
proof summaries
done acknowledgements
sprint reports
stabilization reports
runtime maps
rehabilitation notes
migration notes
verification reports
post-sprint closeout notes

Default location:
/Users/AGENT/.openclaw/workspace/docs/rebuild/

Visibility:
internal only

Examples:
ACME_FULFILLMENT_V1_STATUS.md
WATCHDOG_STABILIZATION_REPORT.md
OPENCLAW_RUNTIME_SOURCE_MAP.md

────────────────────────────────────────

CANONICAL_ENGINEERING_DOC

Used for:
architecture docs
subsystem specs
repo doctrine
technical references
postmortems
source-of-truth design docs
operator doctrines
CLI specs
engineering task packets

Default location:
canonical repo docs/ directory for the subsystem

Examples:
openclaw-ops/docs/
octrigeunit/docs/
acme-site/docs/internal/ if specifically engineering and repo-local

Visibility:
internal / canonical

Examples:
RADCHECK_v2_ARCHITECTURE.md
REPO_DOCTRINE.md
DOCUMENT_ROUTING_DOCTRINE.md

────────────────────────────────────────

PRODUCT_DOCUMENTATION

Used for:
public product pages
customer-facing docs
install guides
feature explanations
pricing support docs
operator-facing customer docs
product overviews

Default location:
/Users/AGENT/.openclaw/workspace/acme-site/docs/products/
/Users/AGENT/.openclaw/workspace/acme-site/content/docs/

Visibility:
public or semi-public

Examples:
docs/products/radcheck/overview.mdx
content/docs/radcheck/score-explained.md

Rule:
Do not place internal status, proof, or sprint documents here.

────────────────────────────────────────

WORKING_NOTE

Used for:
scratch notes
temporary task notes
in-progress captures
memory fragments
non-authoritative thinking
parking-lot notes

Default location:
memory/
notes/
temporary workspace area

Visibility:
internal, temporary, non-authoritative

Rule:
Working notes are not canonical truth.

────────────────────────────────────────

SECTION 3 - ROUTING RULES

Rule 1
If the document reports progress, proof, status, or completion, it is usually an INTERNAL_OPERATIONAL_RECORD.

Rule 2
If the document defines architecture or doctrine, it is usually a CANONICAL_ENGINEERING_DOC.

Rule 3
If the document is intended for customers or public readers, it is PRODUCT_DOCUMENTATION.

Rule 4
If the document is temporary, exploratory, or incomplete, it is a WORKING_NOTE.

Rule 5
If there is any doubt, default to INTERNAL_OPERATIONAL_RECORD, not public docs.

────────────────────────────────────────

SECTION 4 - MANDATORY SAVE PREAMBLE

Before saving any new document, respond with:

document_class:
target_location:
public_or_internal:

If the class is not obvious, stop and ask.

────────────────────────────────────────

SECTION 5 - NEVER DO THIS

Never save internal proof bundles or status records into:
acme-site public docs
customer-facing product pages
marketing docs

Never treat working notes as canonical engineering truth.

Never duplicate the same document across multiple classes unless explicitly instructed.

────────────────────────────────────────

SECTION 6 - SPECIAL CASES

Proof bundles
INTERNAL_OPERATIONAL_RECORD

Runtime maps
INTERNAL_OPERATIONAL_RECORD or CANONICAL_ENGINEERING_DOC depending on intended permanence

Architecture specs
CANONICAL_ENGINEERING_DOC

Fulfillment status reports
INTERNAL_OPERATIONAL_RECORD

Product install guides
PRODUCT_DOCUMENTATION

Scratch investigations
WORKING_NOTE

────────────────────────────────────────

SECTION 7 - SUCCESS CONDITION

This doctrine is working when:

internal status docs stop appearing in public repos
engineering docs live in the correct canonical repo
agents stop asking where to save obvious records
older records become easier to find by class

────────────────────────────────────────

END OF DOCUMENT