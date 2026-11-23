#!/bin/zsh
# Puts samples/edge-demo into the local demo AEM: table cells copied and an SVG without alt, edge cases of
# eval/cases.json. Local author on 127.0.0.1 with its default login only.
# Run again to reset.
#   ./samples/load_edge_demo.sh
set -e
A=http://127.0.0.1:4502
AUTH=admin:admin
ROOT=${ROOT:-/content/dam/edge-demo}
cd "$(dirname "$0")/edge-demo"
up() {  # file, relative to the sample; content type
  local dir=$(dirname "$1"); local target="$ROOT/$dir"; [ "$dir" = "." ] && target="$ROOT"
  curl -s -o /dev/null -u $AUTH -F "file=@$1;type=$2" --form-string "fileName=$(basename $1)" "$A$target.createasset.html"
}
curl -s -o /dev/null -u $AUTH -X DELETE $A$ROOT; sleep 5
curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" -F "jcr:title=Ledgerline edge cases" $A$ROOT
for d in images topics; do curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" $A$ROOT/$d; done
for f in images/*.svg; do up $f image/svg+xml; sleep 1; done
sleep 10   # the images must exist before the topics, so that AEM stores their references by GUID
for f in topics/*.dita edge_guide.ditamap; do up $f application/xml; sleep 2; done
echo "done. Open $ROOT/edge_guide.ditamap in the editor and run Health check."
