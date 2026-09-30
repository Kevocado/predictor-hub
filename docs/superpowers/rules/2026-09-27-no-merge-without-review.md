# Standing rule: no merge without a review

**In force until the reviewer session (Claude) returns, Tuesday 2026-09-29
morning.** Kevin, 2026-09-27.

The no-merge rule was lifted on 2026-09-27 so work could ship without the
reviewer session available. Lifting it was intended to allow **merging reviewed
work**, not to skip the review. It was used that way within the hour, and the
result was a direct push to `main` that put the wrong sport's workflow into NFL's
repo.

## The rule

**No commit reaches `main` without passing `superpowers:requesting-code-review`
first.** Merging is permitted. Unreviewed merging is not.

Concretely, for every change in every repo:

1. Run the repo's tests and read the diff, as always.
2. Run `/requesting-code-review` (or `superpowers:requesting-code-review`) on the
   change. Read the findings. Fix what it finds, test-first, in the same branch.
3. Only then merge — via a PR, never `git push origin <branch>:main`.
4. Record the review's outcome in the commit body, so the next person can see a
   change was reviewed and what the review said.

## What is still forbidden, rule lifted or not

- **No `git push origin <branch>:main`.** Every change goes through a PR. A
  direct push cannot be reviewed, cannot be reverted cleanly, and bypasses the
  one check that catches most of what goes wrong.
- **No force-push to `main` except to undo a bad direct push.** That is the only
  case, it is announced before it happens, and the correct content follows as a
  reviewed PR rather than in the same push. (Used once: 2026-09-27, NFL, to undo
  exactly this mistake.)
- **No merge of a review that was not run**, and no "the tests are green so it is
  reviewed". A green suite is not a review. It has now let through: a cron that
  ran the wrong sport's module, and a guard that could be silenced by making the
  thing it guards bad.
- **A review that finds something is not merged on the grounds that the finding
  is minor.** The findings on 2026-09-27 were a 767% quota increase and a
  cross-wired workflow. Neither looked minor once measured.

## Why the tests did not catch it

Worth recording, because it is the reason a review is not optional here even with
a full suite.

The cron test was written to assert that the workflow's windows agree with the
sport's schedule. Put CFB's workflow into NFL's repo and it passed. The reason:
`_is_window` decided "is this a window?" by asking whether it overlapped that
sport's dense hours — so a workflow naming the *wrong* hours was classified as
"this sport has no window at all", the test took its "unchanged by design" path,
and skipped. A guard that decides whether something counts as a guard by asking
whether the thing is any good can always be silenced by making the thing bad.

Three earlier versions of the same predicate had the same class of problem in
other directions. The fourth is shape-only, with agreement checked separately, and
now rejects both CFB's file in NFL and NFL's file in CFB.

**So: coverage and content checks live in tests. Judgment calls — is this the right
scope, is this the right cost, is this the right repo — live in review.**

## On expiry

When the reviewer session returns, this rule lapses and the normal cycle resumes:
the reviewer reviews and merges, and posts the next instructions. The refresh and
explainer work merged in the interim is documented in the commit bodies, so the
reviewer can audit it after the fact — which is the point of recording outcomes
rather than just verdicts.
