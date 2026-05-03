# Project Documentation

This directory holds project knowledge that should stay close to the codebase.

## `adr/`

Architecture Decision Records document meaningful technical decisions after the team has chosen a direction.

Use an ADR when a decision changes architecture, dependencies, data flow, deployment, security posture, or another durable technical constraint. ADRs should be short, specific, and decision-focused.

Recommended ADR format:

```md
# ADR 0001: Short Decision Title

## Status

Proposed | Accepted | Superseded

## Context

What problem, constraint, or tradeoff led to this decision?

## Decision

What did we decide?

## Consequences

What improves, what gets harder, and what follow-up work does this create?

## Alternatives Considered

What other options were seriously considered, and why were they not chosen?
```

## `prd/`

Product Requirements Documents describe what the product or feature should accomplish before implementation details take over.

Use a PRD for features, workflows, product behavior, user-facing requirements, and acceptance criteria. PRDs should define the problem and desired outcome without becoming an implementation plan.

Recommended PRD filenames should be short, lowercase, and descriptive:

```text
chat-ui.md
auth-flow.md
document-upload.md
```

Recommended PRD format:

```md
# Feature or Product Area Name

## Summary

Briefly describe the feature and why it matters.

## Goals

What should this work accomplish?

## Non-Goals

What is intentionally out of scope?

## Users

Who is this for, and what do they need?

## Requirements

- Requirement 1
- Requirement 2
- Requirement 3

## Acceptance Criteria

- Observable condition that must be true for the work to be done
- Observable condition that must be true for the work to be done

## Open Questions

- Question that needs resolution
```

## `notes/`

Notes are informal project memory. Use this folder for meeting notes, research summaries, brainstorming, rough comparisons, and useful context that is not formal enough for an ADR or PRD.

Keep `notes/` flat unless the volume of files becomes hard to scan.
