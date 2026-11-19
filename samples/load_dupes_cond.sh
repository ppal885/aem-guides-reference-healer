#!/bin/zsh
# Puts samples/dupes-cond into the local demo AEM: copies with the same words for other readers, to
# check that a Fix keeps them apart and keeps their conditions. Local author on 127.0.0.1 with its default login only.
# Run again to reset.
#   ./samples/load_dupes_blocks.sh
set -e
A=http://127.0.0.1:4502
AUTH=admin:admin
ROOT=${ROOT:-/content/dam/dupes-cond}
cd "$(dirname "$0")/dupes-cond"
up() {  # file, relative to the sample
  local dir=$(dirname "$1"); local target="$ROOT/$dir"; [ "$dir" = "." ] && target="$ROOT"
  curl -s -o /dev/null -u $AUTH -F "file=@$1;type=application/xml" -F "fileName=$(basename $1)" "$A$target.createasset.html"
}
curl -s -o /dev/null -u $AUTH -X DELETE $A$ROOT; sleep 5
curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" -F "jcr:title=Ledgerline access (conditions demo)" $A$ROOT
for d in concepts; do curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" $A$ROOT/$d; done
for f in $(ls concepts/*.dita) cond_guide.ditamap; do up $f; sleep 2; done
echo "done. Open $ROOT/cond_guide.ditamap in the editor and run Health check."
