#!/bin/zsh
# Puts samples/names-demo into the local demo AEM: made-up topics that write a name more than one way,
# to check how they are found and made one spelling. Local author on 127.0.0.1 with its default login only.
# Run again to reset.
#   ./samples/load_names_demo.sh
set -e
A=http://127.0.0.1:4502
AUTH=admin:admin
ROOT=${ROOT:-/content/dam/names-demo}
cd "$(dirname "$0")/names-demo"
up() {  # file, relative to the sample; content type
  local dir=$(dirname "$1"); local target="$ROOT/$dir"; [ "$dir" = "." ] && target="$ROOT"
  curl -s -o /dev/null -u $AUTH -F "file=@$1;type=$2" --form-string "fileName=$(basename $1)" "$A$target.createasset.html"
}
curl -s -o /dev/null -u $AUTH -X DELETE $A$ROOT; sleep 5
curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" -F "jcr:title=Harbor gateway (names demo)" $A$ROOT
for d in topics; do curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" $A$ROOT/$d; done
for f in topics/*.dita names_guide.ditamap; do up $f application/xml; sleep 2; done
echo "done. Open $ROOT/names_guide.ditamap in the editor and run Health check with Broken links."
