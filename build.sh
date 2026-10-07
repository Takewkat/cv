#!/usr/bin/env bash
# Renders every variant of the given profiles to one-page A4 PDFs and PNG previews with headless Chrome.
# Usage: ./build.sh              -> every profiles/<id>/ whose name does not start with _
#        ./build.sh <you> _template
# Output: out/<id>/<fileStem>-<variant>.pdf (+ .png preview on macOS)
# Then stamps the PDF metadata and fails when a PDF is not one page or its ATS text is broken (atscheck.py).
set -euo pipefail

cd "$(dirname "$0")"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
flags=(--headless=new --disable-gpu --no-pdf-header-footer --virtual-time-budget=8000)
# Linux CI runners have no usable Chrome sandbox
[ "${CI:-}" = true ] && flags+=(--no-sandbox)

if [ $# -eq 0 ]; then
  for d in profiles/*/; do
    id="$(basename "$d")"
    case "$id" in _*) continue ;; esac
    set -- "$@" "$id"
  done
  # A fresh copy has only the example: build it so CI stays green until a profile is added
  [ $# -gt 0 ] || { echo "no profile yet, building the _template example (copy it to profiles/<you>)"; set -- _template; }
fi

failed=0
for id in "$@"; do
  summary="$(node read-profile.js "$id" --summary)" || { failed=1; continue; }
  read -r stem variants <<<"$summary"
  mkdir -p "out/$id"
  for v in $variants; do
    pdf="out/$id/$stem-$v.pdf"
    rm -f "$pdf"
    "$CHROME" "${flags[@]}" --print-to-pdf="$pdf" "file://$PWD/index.html?profile=$id&v=$v" 2>/dev/null
    command -v sips >/dev/null && sips -s format png "$pdf" --out "out/$id/$stem-$v.png" >/dev/null
    echo "built $pdf"
  done
  python3 atscheck.py "$id" || failed=1
done

exit "$failed"
