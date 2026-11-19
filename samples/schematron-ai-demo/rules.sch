<?xml version="1.0" encoding="UTF-8"?>
<!-- Made-up house rules for the AI fix demo ("Ledgerline"). None has a Schematron Quick Fix: six are
     about structure (code), six about wording (text). Content Health asks a model for a fix on demand
     and offers it only when this Schematron, run again, no longer reports the finding. -->
<schema xmlns="http://purl.oclc.org/dsdl/schematron" queryBinding="xslt2">
  
    <pattern><rule context="note"><assert id="c-note-type" test="@type" role="warning">A note says which kind of note it is (type).</assert></rule></pattern>
    <pattern><rule context="image"><assert id="c-image-alt" test="normalize-space(alt)" role="error">An image has alternative text (alt).</assert></rule></pattern>
    <pattern><rule context="p"><report id="c-no-bold" test="b" role="warning">Bold is not used in a paragraph; interface names are marked as uicontrol.</report></rule></pattern>
    <pattern><rule context="table"><assert id="c-table-title" test="title" role="warning">A table has a title.</assert></rule></pattern>
    <pattern><rule context="section"><assert id="c-section-id" test="@id" role="info">A section has an id, so other topics can link to it.</assert></rule></pattern>
    <pattern><rule context="fig"><assert id="c-fig-title" test="title" role="warning">A figure has a title.</assert></rule></pattern>
  
    <pattern><rule context="topic/title"><assert id="t-title-length" test="string-length(normalize-space(.)) le 60" role="warning">A title has at most 60 characters.</assert></rule></pattern>
    <pattern><rule context="shortdesc"><assert id="t-shortdesc-words" test="count(tokenize(normalize-space(.), ' ')) le 30" role="warning">A short description has at most 30 words.</assert></rule></pattern>
    <pattern><rule context="p | cmd"><assert id="t-no-click" test="not(matches(., '(^|\W)Click(\W|$)'))" role="info">Write "Select", not "Click".</assert></rule></pattern>
    <pattern><rule context="p | cmd"><assert id="t-no-please" test="not(matches(., '(^|\W)[Pp]lease(\W|$)'))" role="info">Instructions do not say "please".</assert></rule></pattern>
    <pattern><rule context="p"><assert id="t-no-exclamation" test="not(contains(., '!'))" role="info">A paragraph does not end with an exclamation mark.</assert></rule></pattern>
    <pattern><rule context="p"><assert id="t-sentence-length" test="every $s in tokenize(normalize-space(.), '\.\s') satisfies count(tokenize($s, ' ')) le 25" role="warning">A sentence has at most 25 words.</assert></rule></pattern>
</schema>
