#!/bin/sh
# Loads the small image and duplicate id sample into the local AEM (default admin on 127.0.0.1).
#   ./samples/load_image_demo.sh            -> /content/dam/image-demo
#   ROOT=/content/dam/x ./samples/load_image_demo.sh
# What is in it: a map key renamed (product-logo -> brand-logo), a key whose image moved
# (images/wiring.png -> images/diagrams/wiring.png), an image used by path that moved
# (images/panel.png -> images/ui/panel.png), and ids used two and three times in one topic.
# Run Health check with a preset that has "Broken links" and "Duplicate IDs".
set -e
cd "$(dirname "$0")/image-demo"
A=${AEM:-http://127.0.0.1:4502}; AUTH=${AUTH:-admin:admin}; ROOT=${ROOT:-/content/dam/image-demo}
curl -s -o /dev/null -u $AUTH -X DELETE $A$ROOT
for d in "" /images /images/diagrams /images/ui; do curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" $A$ROOT$d; done
up() { curl -s -o /dev/null -u $AUTH -F "file=@$1;type=$3" -F "fileName=$4" "$A$2.createasset.html"; }
up logo.png $ROOT/images image/png logo.png
up logo.png $ROOT/images/diagrams image/png wiring.png
up logo.png $ROOT/images/ui image/png panel.png
up a.dita $ROOT application/xml a.dita
up m.ditamap $ROOT application/xml m.ditamap
echo "Loaded. Open $ROOT/m.ditamap in the editor."
