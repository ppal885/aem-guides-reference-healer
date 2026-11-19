<?xml version="1.0" encoding="UTF-8"?>
<!-- Made-up house rules for the Schematron fix demo ("Ledgerline"). Four rules carry a Schematron
     Quick Fix (sqf:fix) that Content Health computes and offers; two have none and are only reported. -->
<schema xmlns="http://purl.oclc.org/dsdl/schematron"
        xmlns:sqf="http://www.schematron-quickfix.com/validator/process" queryBinding="xslt2">
  <pattern id="house-rules">
    <rule context="note">
      <assert id="note-type" test="@type" role="warning" sqf:fix="note-caution">A note says which kind of note it is (type).</assert>
      <sqf:fix id="note-caution">
        <sqf:description><sqf:title>Make it a caution</sqf:title></sqf:description>
        <sqf:add node-type="attribute" target="type">caution</sqf:add>
      </sqf:fix>
    </rule>
    <rule context="p">
      <report id="p-bold" test="b" role="warning" sqf:fix="p-unbold">Bold is not used inside a paragraph; use uicontrol for interface names.</report>
      <sqf:fix id="p-unbold">
        <sqf:description><sqf:title>Make bold text a uicontrol</sqf:title></sqf:description>
        <sqf:replace match="b" node-type="element" target="uicontrol"><sqf:copy-of select="node()"/></sqf:replace>
      </sqf:fix>
    </rule>
    <rule context="shortdesc">
      <assert id="sd-click" test="not(contains(., 'Click'))" role="info" sqf:fix="sd-select">Write "Select", not "Click".</assert>
      <sqf:fix id="sd-select">
        <sqf:description><sqf:title>Replace "Click" with "Select"</sqf:title></sqf:description>
        <sqf:stringReplace match="text()" regex="Click">Select</sqf:stringReplace>
      </sqf:fix>
    </rule>
    <rule context="section">
      <assert id="section-draft" test="not(@outputclass = 'draft')" role="error" sqf:fix="section-undraft">A section marked as a draft is not published.</assert>
      <sqf:fix id="section-undraft">
        <sqf:description><sqf:title>Remove the draft mark</sqf:title></sqf:description>
        <sqf:delete match="@outputclass"/>
      </sqf:fix>
    </rule>
    <rule context="title">
      <assert id="title-length" test="string-length(normalize-space(.)) le 60" role="warning">A title has at most 60 characters.</assert>
    </rule>
    <rule context="topic">
      <assert id="topic-shortdesc" test="shortdesc" role="warning">A topic has a short description.</assert>
    </rule>
  </pattern>
</schema>
