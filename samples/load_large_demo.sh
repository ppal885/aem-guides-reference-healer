#!/bin/zsh
# Puts the large sample into the local demo AEM in its broken state (garage-week PoC).
# Local author on 127.0.0.1 with its default login only. Run again to reset after "Fix all".
#   ./samples/load_large_demo.sh
set -e
A=http://127.0.0.1:4502
AUTH=admin:admin
ROOT=/content/dam/large-demo
cd "$(dirname "$0")/large-demo"

up() {  # version folder, relative file
  local dir=$(dirname "$2"); [ "$dir" = "." ] && dir=""
  curl -s -o /dev/null -u $AUTH -F "file=@$1/$2;type=application/xml" -F "fileName=$(basename $2)" "$A$ROOT/$dir.createasset.html"
}
stored() { curl -s -u $AUTH "$A$ROOT/$1/jcr:content/renditions/original/jcr:content/jcr:data"; }

curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" -F "jcr:title=Atlas Cloud guide (large reference demo)" $A$ROOT
for d in $(cd v1 && ls -d */ | tr -d /); do curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" $A$ROOT/$d; done

echo "1/3 the set as it was (v1): shared files, then topics, then the map"
for f in shared/warnings.dita shared/paragraphs.dita reference/limits.dita reference/errors.dita; do up v1 $f; done
sleep 20
for f in $(cd v1 && ls */*.dita | grep -v -E "^(shared|reference)/"); do up v1 $f; done
up v1 atlas_guide.ditamap
until stored atlas_guide.ditamap | grep -q 'topicref href="GUID-'; do sleep 5; done
until stored migration/migration_test_20.dita | grep -q 'conref="GUID-'; do sleep 5; done

echo "2/3 the clean-up of the shared content (v2): renamed, reworded, moved, merged and removed pieces"
# Every file that is new or different in v2; the map last, so its references find their targets.
for f in $(cd v2 && ls */*.dita); do cmp -s v1/$f v2/$f || up v2 $f; done
sleep 10
up v2 atlas_guide.ditamap
until stored atlas_guide.ditamap | grep -q 'keys="shared-warnings"' && stored atlas_guide.ditamap | grep -q 'topicref href="GUID-'; do sleep 5; done
# After a reset the two files that only exist in v2 must be back to their v2 content as well.
until stored reference/storage.dita | grep -q 'id="object-size"'; do sleep 3; done

# AEM rebuilds a map's key space when the map is saved through the Guides asset API, not when it is
# overwritten by an upload. Without this save its Broken links report keeps the keys of v1.
curl -s -u $AUTH "$A/bin/guides/v1/asset?path=$ROOT/atlas_guide.ditamap" \
  | python3 -c "import json,sys,gzip; sys.stdout.buffer.write(gzip.compress(json.load(sys.stdin)['content'].encode('utf-8')))" > /tmp/atlas_guide.$$.gz
curl -s -o /dev/null -u $AUTH -F "file=@/tmp/atlas_guide.$$.gz;type=application/gzip" -F "resourceType=GUIDES_RESOURCE" \
  -F "path=$ROOT/atlas_guide.ditamap" "$A/bin/guides/v1/asset/update"
rm -f /tmp/atlas_guide.$$.gz
sleep 20

# One topic of another guide that reuses a warning of this one. It is not in the map, so the
# agents never see it; the report must still say that the same break exists outside the map.
OUTSIDE=/content/dam/large-demo-outside
curl -s -o /dev/null -u $AUTH -F "jcr:primaryType=sling:Folder" -F "jcr:title=Another guide (uses the shared warnings)" $A$OUTSIDE
printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>' '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">' \
  '<topic id="partner_onboarding"><title>Partner onboarding</title><body>' \
  '<note conref="../large-demo/shared/warnings.dita#warnings/admin-only"/>' \
  '<p>Ask your account manager for a partner organisation.</p></body></topic>' > /tmp/partner_onboarding.$$.dita
curl -s -o /dev/null -u $AUTH -F "file=@/tmp/partner_onboarding.$$.dita;type=application/xml" -F "fileName=partner_onboarding.dita" "$A$OUTSIDE.createasset.html"
rm -f /tmp/partner_onboarding.$$.dita

# A filter for one output of the map: the "AEM Sites" output leaves out audience="internal". The
# compare box then shows that this output publishes fewer of the affected references than the others.
curl -s -o /dev/null -u $AUTH -F "file=@customer.ditaval;type=application/xml" -F "fileName=customer.ditaval" "$A$ROOT.createasset.html"
python3 ../set_output_filter.py $ROOT/atlas_guide.ditamap aemsites $ROOT/customer.ditaval

echo "3/3 done. Open $ROOT/atlas_guide.ditamap in the editor and run Health check with Broken links."
