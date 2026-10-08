---
name: new-application
description: Handles one job application end to end from a posting (link, pasted text, or both) - company research, requirements against the CV, a one-off tailored CV, short and long motivation in the posting's language, and a report. Use when the user shares a job posting or a job-board link (Welcome to the Jungle, LinkedIn, France Travail, Indeed, welcomekit), or says "job posting", "offre", "вакансия", "apply", "new application".
---

# New application

Input: a posting link, its text, or both. Output: `applications/<date>-<company>-<role>/` holding `posting.md`, `gap.txt`, the CV PDF (and its PNG preview), `cv-variant.patch` when the CV is tailored, `motivation.md`, and a report in chat.

Run every step without asking. Stop only at the gates marked **Ask**.

## 1. Posting

- Welcome to the Jungle refuses automated fetches (403, or an empty 202 to curl). With only a link: search the title on France Travail, the company's welcomekit page or Indeed. No full text anywhere: **Ask** for the pasted text.
- Write it to a temp file: first line `<Company> - <Role> - <contract> - <city>`, second line the link, then the posting verbatim. Replace the GDPR or legal block with one line saying it is omitted.

## 2. Research (in parallel with 3 and 4, in a sub-agent when the tool has one)

A URL for every claim, "unverified" when not confirmed. Steps 5 to 7 wait for it. A constraint that may block the user (nationality, clearance, work permit, language): **Ask** before step 5, after checking `facts.md`.

| Topic | Find |
|---|---|
| What it is | sector, legal status (public body, startup, defense), size, funding |
| Constraints | nationality, security clearance, work permit, working language |
| Stack and team | what the platform runs on, migrations under way, the stacks of their other tech postings, public repos |
| Conditions | contract, salary range, remote days |
| Stability | budget, leadership changes, restructuring, layoffs, employee reviews |
| Interviews | the steps the posting lists |

## 3. Folder and base variant

- `./jd-gap.py --variant <v> <temp file>` for every variant of the profile. Pick the base by role type first (each variant's label and headline say what it targets), score second: the score is noisy on postings in another language than the CV, where common words count as missing.
- `./new-application.sh "<Company>" "<Role>" <base> < <temp file>`. ASCII names without `&` or `/`: the slug turns accents into dashes, and the motivation template is filled by `sed`.

## 4. Requirements against evidence

One table: requirement | evidence | yes, partial or no.

Evidence comes, in this order, from `profiles/<id>/content.js`, `profiles/<id>/facts.md`, and the sources `facts.md` lists (repos and their git history, documents the tool can open). A claim with no evidence goes in neither the CV nor the letter: it goes under "to confirm" in the report. Never use a "To confirm" line of `facts.md`. A training project is never presented as work: it is named as training, though a skill learned there may be listed as a skill. Numbers show a change or what was caught (before and after, failures found behind a green report), never a raw volume such as a test count or a run time, which reads small out of context.

## 5. CV

- The base variant already answers the must-haves: copy `out/<id>/<stem>-<base>.pdf` (and `.png`) into the folder after `./build.sh <id>`. Done.
- Otherwise tailor a one-off variant X. Never add a permanent variant for one application: every variant becomes a filter on the board.
  1. `git status --short -- profiles/<id>/content.js` must be empty, else **Ask**.
  2. In `content.js`, add variant `X` after the last one, its key written literally `X: {` (the script looks for it): start from the base, reuse shared blocks, take bullets from other variants where they answer a requirement. Headline: the posting's role. Profile: the link to the employer's domain when there is one. Label: the role, short.
  3. `./application-cv.sh applications/<dir>`: saves the diff as `cv-variant.patch`, builds, copies the PDF and PNG, rewrites `gap.txt` against X, restores `content.js`.
  4. Read the PNG: one page, the last Education line clear of the bottom of the page, no OVERFLOW text, the header inside its band. Too long: shorten bullets; do not append to an org name, a wrapped job line costs a line.
  5. To fix after a successful run (`content.js` restored): `git apply applications/<dir>/cv-variant.patch`, edit, run step 3 again. When the script stops at the build (two pages, OVERFLOW), X is still in `content.js`: read the FAIL lines and `out/<id>/<stem>-X.png`, edit in place, run step 3 again.

## 6. Motivation (`motivation.md`)

- Fill both sections of the template, headings translated to the posting's language, and drop the comments. The job title as posted.
- Short (form field): 2 to 4 sentences. What you do that matches the role's core, one or two numbers, the domain link, what you want to do there.
- Long (letter): about 300 words. Why this organisation; one paragraph per section of the posting, led by a bold label, with proofs; a closing tied to a current project found in step 2; signed with the CV name.
- Only claims from step 4.
- Gendered languages: agree with the gender `facts.md` states; when it states none, rephrase without gendered agreement (in French, no motivé(e) or ravi(e)).

## 7. Report (in the user's language)

1. Verdict, one line: the fit and the main gap.
2. Company: the step 2 table, risks first.
3. The requirements table.
4. What the CV changes against the base; the claims to confirm.
5. Interview prep from the process steps.
6. Files created. Nothing committed. On the board: CV "Other" with a note naming the base (for example "Data Engineer, from main"), or the variant itself when sent as is.

When the user confirms a fact during the conversation, add it to `facts.md` with its source and move it out of "To confirm".
