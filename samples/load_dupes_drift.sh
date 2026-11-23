#!/bin/zsh
# Puts samples/dupes-drift into the local demo AEM: copies of one sentence that no longer match, for
# the "Keep copies" mode. Local author on 127.0.0.1 with its default login only. Run again to reset.
#   ./samples/load_dupes_drift.sh
set -e
A=http://127.0.0.1:4502
AUTH=admin:admin
ROOT=${ROOT:-/content/dam/dupes-drift}
cd "$(dirname "$0")/dupes-drift"
up() {  # file, relative to the sample
  local dir=$(dirname "$1"); local target="$ROOT/$dir"; [ "$dir" = "." ] && target="$ROOT"
  curl -s -o /dev/null -u $AUTH -F "file=@$1;type=application/xml" --form-string "fileName=$(basename $1)" "$A$target.createasset.html"
}
curl -s -o /dev/null -u $AUTH -X DELETE $A$ROOT; sleep 5
curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" -F "jcr:title=Ledgerline closing (copies that drifted)" $A$ROOT
curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" $A$ROOT/topics
# The checklist first: a link is stored by the GUID of a file that exists when it is uploaded.
up topics/checklist.dita; sleep 3
for f in $(ls topics/*.dita | grep -v checklist) drift_guide.ditamap; do up $f; sleep 2; done
echo "done. Open $ROOT/drift_guide.ditamap in the editor, run Health check, and open Repeated text."
