#!/bin/zsh
# Puts samples/dupes-demo into the local demo AEM: a guide with text copied into its topics.
# Local author on 127.0.0.1 with its default login only. Run again to reset.
#   ./samples/load_dupes_demo.sh
set -e
A=http://127.0.0.1:4502
AUTH=admin:admin
ROOT=${ROOT:-/content/dam/dupes-demo}
cd "$(dirname "$0")/dupes-demo"
up() {  # file, relative to the sample
  local dir=$(dirname "$1"); local target="$ROOT/$dir"; [ "$dir" = "." ] && target="$ROOT"
  curl -s -o /dev/null -u $AUTH -F "file=@$1;type=application/xml" -F "fileName=$(basename $1)" "$A$target.createasset.html"
}
curl -s -o /dev/null -u $AUTH -X DELETE $A$ROOT; sleep 5
curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" -F "jcr:title=Ledgerline guide (copied text demo)" $A$ROOT
for d in reuse tasks release guides; do curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" $A$ROOT/$d; done
# The library first: a conref is stored by the GUID of a file that exists when it is uploaded.
for f in reuse/library.dita $(ls tasks/*.dita release/*.dita) $(ls guides/*.ditamap) ledger_guide.ditamap; do up $f; sleep 3; done
echo "done. Open $ROOT/ledger_guide.ditamap in the editor and run Health check with Broken links."
