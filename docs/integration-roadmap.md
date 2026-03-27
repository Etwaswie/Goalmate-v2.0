# GoalMate Integration Roadmap

## Base Decision

The technical base for the unified branch is `foundation/auth-postgres`.

This means the unified code keeps:

- PostgreSQL compatibility and staging runtime
- auth, sessions, memberships, scopes
- invitation-code onboarding
- organizer self-serve onboarding
- organizer launch center and content packs

## Product Logic To Pull From `main`

The following product layers from Yulia's branch should be integrated step by step on top of the shared base:

1. Creator content CRUD
   - edit module
   - delete module
   - edit lesson/task
   - delete lesson/task

2. Program lifecycle
   - draft
   - ready
   - active
   - archived

3. Participant lesson flow
   - program structure by module
   - open lesson
   - start lesson
   - complete lesson

4. Attachments
   - files and materials inside content

5. Comments and ratings
   - participant feedback inside lesson flow

6. Creator analytics 2.0
   - content performance
   - top participants
   - engagement diagnostics

## Merge Principle

Do not blindly replace the current architecture with the older `main` implementation.

Use this rule for further reconciliation:

- keep infra, auth, Postgres, staging and permissions from `foundation/auth-postgres`
- port product UX and content ideas from `main`
- verify local run and staging after each slice

## Next Recommended Slice

The next concrete reconciliation step is:

1. creator content CRUD
2. program lifecycle

These two slices provide the most product value while staying compatible with the current staging foundation.
