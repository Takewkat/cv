# Agent guide

CV as code (`profiles/<id>/content.js` rendered to one-page A4 PDFs) and a private job-application board. See `README.md`.

## A job posting arrives

When the user gives a job posting (a link, its text, or both), run `.claude/skills/new-application/SKILL.md` end to end, without asking before each step.

## Commands

```
./build.sh <id>                                        # every variant -> out/<id>/*.pdf, ATS check, snapshots/
./new-application.sh "<Company>" "<Role>" <variant> < posting.txt   # applications/<date>-<company>-<role>/
./jd-gap.py --variant <v> posting.txt                  # what the posting asks that the variant does not say
./application-cv.sh applications/<dir>                 # one-off CV from variant X, then X removed
./tracker.sh                                           # the board, http://127.0.0.1:8765/
```

## Rules

- A CV or a motivation claims only what `content.js` and `profiles/<id>/facts.md` support. A training project is never presented as work.
- When the user confirms a fact about their experience, add it to `facts.md` with its source.
- No permanent variant for one application: a variant is a filter on the board. One-off CVs are variant X, built by `application-cv.sh` and recorded as "Other".
- `snapshots/` changes only through `build.sh`.
- Commit only when asked.
- Replies: in the user's language, short. The user's own preferences, when any, are at the top of `facts.md`.
