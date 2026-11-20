#!/bin/zsh
# Puts samples/schematron-ask-demo into the local demo AEM: a Schematron with quick fixes and the topics it checks, to
# check Schematron fixes that ask the author for a value or change something outside the element. Local author on 127.0.0.1 with its default login only.
# Run again to reset.
#   ./samples/load_schematron_ask_demo.sh
set -e
A=http://127.0.0.1:4502
AUTH=admin:admin
ROOT=${ROOT:-/content/dam/schematron-ask-demo}
cd "$(dirname "$0")/schematron-ask-demo"
up() {  # file, relative to the sample
  local dir=$(dirname "$1"); local target="$ROOT/$dir"; [ "$dir" = "." ] && target="$ROOT"
  curl -s -o /dev/null -u $AUTH -F "file=@$1;type=application/xml" -F "fileName=$(basename $1)" "$A$target.createasset.html"
}
curl -s -o /dev/null -u $AUTH -X DELETE $A$ROOT; sleep 5
curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" -F "jcr:title=Ledgerline ledgers (Schematron fixes that ask or reach outside)" $A$ROOT
for d in topics; do curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" $A$ROOT/$d; done
for f in rules.sch $(ls topics/*.dita) ledger.ditamap; do up $f; sleep 2; done
echo "done. Open $ROOT/ledger.ditamap; in a Content Health preset select $ROOT/rules.sch for Schematron."
