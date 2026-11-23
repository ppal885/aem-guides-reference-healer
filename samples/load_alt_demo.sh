#!/bin/zsh
# Puts samples/alt-demo into the local demo AEM: made-up images without a useful alt text, to check
# how they are found and suggested. Local author on 127.0.0.1 with its default login only.
# Run again to reset.
#   ./samples/load_alt_demo.sh
set -e
A=http://127.0.0.1:4502
AUTH=admin:admin
ROOT=${ROOT:-/content/dam/alt-demo}
cd "$(dirname "$0")/alt-demo"
up() {  # file, relative to the sample; content type
  local dir=$(dirname "$1"); local target="$ROOT/$dir"; [ "$dir" = "." ] && target="$ROOT"
  curl -s -o /dev/null -u $AUTH -F "file=@$1;type=$2" --form-string "fileName=$(basename $1)" "$A$target.createasset.html"
}
curl -s -o /dev/null -u $AUTH -X DELETE $A$ROOT; sleep 5
curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" -F "jcr:title=Ledgerline images (alt text demo)" $A$ROOT
for d in images topics; do curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" $A$ROOT/$d; done
for f in images/*.png; do up $f image/png; sleep 1; done
sleep 10   # the images must exist before the topics, so that AEM stores their references by GUID
for f in topics/*.dita alt_guide.ditamap; do up $f application/xml; sleep 2; done
echo "done. Open $ROOT/alt_guide.ditamap in the editor and run Health check with the Broken references demo preset (Broken links)."
