#!/usr/bin/env python3
"""Gives one output preset of a map in the local demo AEM a DITAVAL filter (garage-week PoC).

    python3 samples/set_output_filter.py <map path> <preset name, e.g. aemsites> <ditaval path>

Local author on 127.0.0.1 with its default login only. It reads the preset as the Guides endpoint
returns it, sets the filter fields and saves it back the way the editor's preset dialog does.
"""
import base64
import json
import sys
import urllib.parse
import urllib.request

AEM = "http://127.0.0.1:4502"
AUTH = {"Authorization": "Basic " + base64.b64encode(b"admin:admin").decode()}


def main():
    map_path, name, ditaval = sys.argv[1:4]
    url = "%s/bin/guides/presets?mapPath=%s&type=PATH" % (AEM, urllib.parse.quote(map_path))
    presets = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=AUTH)).read())
    preset = next(p for p in presets["localPresets"] if p.get("outputName") == name)
    preset.update(ditaValType="ditaval", ditaValPath=ditaval, ditaValPathList=[ditaval])
    body = urllib.parse.urlencode({":operation": "saveoutput", "outputObj": json.dumps(preset), "cache": "false",
                                   "sourcePath": map_path}).encode()
    request = urllib.request.Request(AEM + "/bin/publishlistener", data=body, headers=AUTH)
    print("saved %s: HTTP %d" % (preset.get("outputTitle"), urllib.request.urlopen(request).status))


if __name__ == "__main__":
    main()
