#!/bin/zsh
# Puts samples/schematron-demo into the local demo AEM: a Schematron with quick fixes and the topics it checks, to
# check the Content Health "Apply fix" on Schematron findings. Local author on 127.0.0.1 with its default login only.
# Run again to reset.
#   ./samples/load_dupes_blocks.sh
set -e
A=http://127.0.0.1:4502
AUTH=admin:admin
ROOT=${ROOT:-/content/dam/schematron-demo}
cd "$(dirname "$0")/schematron-demo"
up() {  # file, relative to the sample
  local dir=$(dirname "$1"); local target="$ROOT/$dir"; [ "$dir" = "." ] && target="$ROOT"
  curl -s -o /dev/null -u $AUTH -F "file=@$1;type=application/xml" -F "fileName=$(basename $1)" "$A$target.createasset.html"
}
curl -s -o /dev/null -u $AUTH -X DELETE $A$ROOT; sleep 5
curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" -F "jcr:title=Ledgerline periods (Schematron fix demo)" $A$ROOT
for d in topics; do curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" $A$ROOT/$d; done
for f in rules.sch $(ls topics/*.dita) periods.ditamap; do up $f; sleep 2; done
echo "done. Open $ROOT/periods.ditamap; in a Content Health preset select $ROOT/rules.sch for Schematron."
