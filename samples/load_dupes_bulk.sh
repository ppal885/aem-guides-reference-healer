#!/bin/zsh
# Puts samples/dupes-bulk into the local demo AEM: 120 topics that share three notes, to time
# "Fix all safe". Local author on 127.0.0.1 with its default login only. Run again to reset.
#   ./samples/load_dupes_bulk.sh
set -e
A=http://127.0.0.1:4502
AUTH=admin:admin
ROOT=${ROOT:-/content/dam/dupes-bulk}
cd "$(dirname "$0")/dupes-bulk"
up() {  # file, relative to the sample
  local dir=$(dirname "$1"); local target="$ROOT/$dir"; [ "$dir" = "." ] && target="$ROOT"
  curl -s -o /dev/null -u $AUTH -F "file=@$1;type=application/xml" -F "fileName=$(basename $1)" "$A$target.createasset.html"
}
curl -s -o /dev/null -u $AUTH -X DELETE $A$ROOT; sleep 5
curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" -F "jcr:title=Ledgerline posting rules (Fix all timing)" $A$ROOT
curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" $A$ROOT/rules
for f in $(ls rules/*.dita) bulk_guide.ditamap; do up $f; done
echo "done. Open $ROOT/bulk_guide.ditamap in the editor and run Health check with the Broken references demo preset (Broken links)."
