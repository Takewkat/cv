#!/usr/bin/env bash
# Builds the one-off CV of one application from variant X, then removes X from the profile,
# so the board gets no new CV filter (the card records it as "Other").
# Usage: ./application-cv.sh applications/<dir>
#        content.js adds variant X: its diff is saved as <dir>/cv-variant.patch, then built
#        content.js is clean:       <dir>/cv-variant.patch is applied, then built (rebuild or tweak a past CV)
# Output: <dir>/<fileStem>.pdf (+ .png on macOS) and <dir>/gap.txt against X; content.js restored on success.
# The profile must be committed, with no other change than variant X.
set -euo pipefail

cd "$(dirname "$0")"
[ $# -eq 1 ] || { echo "usage: $0 applications/<dir>" >&2; exit 1; }
dir="${1%/}"
[ -f "$dir/posting.md" ] || { echo "$dir/posting.md not found" >&2; exit 1; }

profile="${PROFILE:-}"
if [ -z "$profile" ]; then
  for d in profiles/*/; do
    id="$(basename "$d")"
    case "$id" in _*) continue ;; esac
    profile="$id"; break
  done
fi
[ -n "$profile" ] || { echo "no profile yet: cp -R profiles/_template profiles/<you>" >&2; exit 1; }
content="profiles/$profile/content.js"
git ls-files --error-unmatch "$content" >/dev/null 2>&1 || { echo "$content is not committed" >&2; exit 1; }

if git diff --quiet -- "$content"; then
  [ -f "$dir/cv-variant.patch" ] || { echo "write variant X in $content first" >&2; exit 1; }
  git apply "$dir/cv-variant.patch"
else
  git diff -- "$content" | grep '^+ *X: {' >/dev/null || { echo "$content has changes but no variant X" >&2; exit 1; }
  git diff -- "$content" > "$dir/cv-variant.patch"
fi

./build.sh "$profile"
read -r stem _ <<<"$(node read-profile.js "$profile" --summary)"
cp "out/$profile/$stem-X.pdf" "$dir/$stem.pdf"
[ -f "out/$profile/$stem-X.png" ] && cp "out/$profile/$stem-X.png" "$dir/$stem.png"
./jd-gap.py --profile "$profile" --variant X "$dir/posting.md" > "$dir/gap.txt" || true

git checkout -- "$content"
rm -f "snapshots/$profile/$stem-X.txt" "out/$profile/$stem-X".*
echo "built $dir/$stem.pdf from variant X; $content restored"
