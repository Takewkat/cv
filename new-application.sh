#!/usr/bin/env bash
# Creates applications/<date>-<company>-<role>/ with the posting, a motivation draft and the jd-gap result.
# Usage: ./new-application.sh "<Company>" "<Role>" <variant>
#        the posting text is read from the clipboard (pbpaste) or from stdin when piped
set -euo pipefail

cd "$(dirname "$0")"
[ $# -eq 3 ] || { echo "usage: $0 \"<Company>\" \"<Role>\" <variant id in content.js>" >&2; exit 1; }
company="$1"; role="$2"; variant="$3"

slug() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//; s/-$//'; }
dir="applications/$(date +%Y-%m-%d)-$(slug "$company")-$(slug "$role")"
[ -e "$dir" ] && { echo "$dir already exists" >&2; exit 1; }
mkdir -p "$dir"

if [ -t 0 ] && command -v pbpaste >/dev/null; then pbpaste > "$dir/posting.md"; else cat > "$dir/posting.md"; fi
[ -s "$dir/posting.md" ] || echo "(paste the job posting here)" > "$dir/posting.md"

sed -e "s/{{COMPANY}}/$company/" -e "s/{{ROLE}}/$role/" applications/_template/motivation.md > "$dir/motivation.md"
./jd-gap.py --variant "$variant" "$dir/posting.md" > "$dir/gap.txt" || true

echo "created $dir (CV variant $variant)"
command -v open >/dev/null && open "$dir/motivation.md" || true
