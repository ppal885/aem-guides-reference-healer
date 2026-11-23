#!/bin/zsh
# Puts samples/dupes-keys into the local demo AEM: a team that reuses by key, with copied text, to
# check that "Share" and "Fix all safe" make conkeyrefs there. Local author on 127.0.0.1 with its
# default login only. Run again to reset.
#   ./samples/load_dupes_keys.sh
set -e
A=http://127.0.0.1:4502
AUTH=admin:admin
ROOT=${ROOT:-/content/dam/dupes-keys}
cd "$(dirname "$0")/dupes-keys"
up() {  # file, relative to the sample
  local dir=$(dirname "$1"); local target="$ROOT/$dir"; [ "$dir" = "." ] && target="$ROOT"
  curl -s -o /dev/null -u $AUTH -F "file=@$1;type=application/xml" -F "fileName=$(basename $1)" "$A$target.createasset.html"
}
curl -s -o /dev/null -u $AUTH -X DELETE $A$ROOT; sleep 5
curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" -F "jcr:title=Ledgerline posting rules by key" $A$ROOT
for d in library topics; do curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" $A$ROOT/$d; done
for f in library/notes.dita $(ls topics/*.dita) sub.ditamap keys_guide.ditamap other_manual.ditamap; do up $f; done
echo "done. Open $ROOT/keys_guide.ditamap in the editor and run Health check with the Broken references demo preset (Broken links)."
