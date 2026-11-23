#!/bin/zsh
# Puts samples/dupes-markup into the local demo AEM: copied steps and links with markup, to check
# that a shared piece keeps its markup. Local author on 127.0.0.1 with its default login only.
# Run again to reset.
#   ./samples/load_dupes_markup.sh
set -e
A=http://127.0.0.1:4502
AUTH=admin:admin
ROOT=${ROOT:-/content/dam/dupes-markup}
cd "$(dirname "$0")/dupes-markup"
up() {  # file, relative to the sample
  local dir=$(dirname "$1"); local target="$ROOT/$dir"; [ "$dir" = "." ] && target="$ROOT"
  curl -s -o /dev/null -u $AUTH -F "file=@$1;type=application/xml" -F "fileName=$(basename $1)" "$A$target.createasset.html"
}
curl -s -o /dev/null -u $AUTH -X DELETE $A$ROOT; sleep 5
curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" -F "jcr:title=Ledgerline closing steps (markup demo)" $A$ROOT
for d in tasks concepts reference; do curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" $A$ROOT/$d; done
for f in reference/limits.dita $(ls tasks/*.dita concepts/*.dita) steps_guide.ditamap; do up $f; sleep 2; done
echo "done. Open $ROOT/steps_guide.ditamap in the editor and run Health check with the Broken references demo preset (Broken links)."
