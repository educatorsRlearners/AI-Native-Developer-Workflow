# Household Chore Tool — Scope Plan

## Users
- 2 users (you + wife)
- Both have full read/write access
- No admin hierarchy

## Chores
Two types:
1. **Permanently owned chores**
   - You: vacuum, clean drains
   - Wife: empty dishwasher
2. **Free-for-all pool** — either person can claim/complete, no fixed owner

## Completion Tracking
- Full log: checkbox + who did it + when
- Not just a simple checkbox reset

## Frequency
- Per-chore frequency (daily, weekly, monthly, custom) — not a single shared schedule

## Notifications
- Active, in-your-face notifications (not passive, not just in-app indicators)
- Targeting:
  - Permanent chores → owner only gets nagged
  - Free-for-all chores → both people get nagged
- Delivery channels: **web push** (primary) + **email** (fallback)

## Platform
- Backend: **Django**
- Frontend: **Installable PWA** (home-screen app, not just a bookmarked webpage)

## Auth
- Lightweight, no full account system
- PIN or magic link per person

## Open Flags for Later (not scoped yet, just noted)
- Web push on iOS Safari requires the PWA to be added to home screen first — regular Safari tab won't support it. Test early.
- Recurring chore logic (overdue → reset cycle) is the trickiest part of the data model — design carefully before writing views.

## Next Steps (not yet started)
- Design data model (chores, completions, notifications)
- Sketch UI screens
