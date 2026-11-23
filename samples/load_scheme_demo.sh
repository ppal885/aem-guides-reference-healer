#!/bin/zsh
# Puts samples/scheme-demo into the local demo AEM: a subject scheme whose keys were renamed after
# topics used them. Local author on 127.0.0.1 with its default login only. Run again to reset.
#   ./samples/load_scheme_demo.sh
# v1 is loaded first, then the scheme of v2 over it, so that AEM keeps v1 as the scheme's previous
# version: that is what proves a rename.
set -e
A=http://127.0.0.1:4502
AUTH=admin:admin
ROOT=/content/dam/scheme-demo
cd "$(dirname "$0")/scheme-demo"

up() {  # version folder, file
  curl -s -o /dev/null -u $AUTH -F "file=@$1/$2;type=application/xml" -F "fileName=$2" "$A$ROOT.createasset.html"
}

for f in $(cd v1 && ls); do curl -s -o /dev/null -u $AUTH -X DELETE $A$ROOT/$f; done
sleep 5
curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" -F "jcr:title=Agent guide (subject scheme demo)" $A$ROOT

echo "1/2 as it was written (v1): the scheme, the topics, then the map"
for f in console_values.ditamap install_agent.dita remove_agent.dita rotate_keys.dita agent_guide.ditamap; do up v1 $f; sleep 3; done
sleep 10

echo "2/2 the scheme's clean-up (v2): linux -> gnu-linux, admin -> administrator, mac -> macos, bsd removed"
up v2 console_values.ditamap
sleep 10
echo "done. Open $ROOT/agent_guide.ditamap in the editor and run Health check with the Broken references demo preset (Broken links)."
