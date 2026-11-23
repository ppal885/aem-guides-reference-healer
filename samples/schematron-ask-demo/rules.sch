<?xml version="1.0" encoding="UTF-8"?>
<!-- Made-up house rules for the Schematron fix demo ("Ledgerline"). Each rule carries a Schematron Quick Fix
     (sqf:fix) of a kind Content Health could not compute before: three ask the author for a value
     (sqf:user-entry), three change something outside the element the rule fired on. -->
<schema xmlns="http://purl.oclc.org/dsdl/schematron"
        xmlns:sqf="http://www.schematron-quickfix.com/validator/process" queryBinding="xslt2">
  <pattern id="ask-the-author">
    <rule context="image">
      <assert id="image-alt" test="normalize-space(alt) or normalize-space(@alt)" role="warning" sqf:fix="image-add-alt">An image has alternative text (alt).</assert>
      <sqf:fix id="image-add-alt">
        <sqf:description><sqf:title>Add alternative text</sqf:title></sqf:description>
        <sqf:user-entry name="alt" default="replace(substring-before(tokenize(@href, '/')[last()], '.'), '[-_]', ' ')">
          <sqf:description><sqf:title>What does the image show?</sqf:title></sqf:description>
        </sqf:user-entry>
        <!-- An <alt> element, as DITA 1.3 has it (the alt attribute is the older way), first in the image. -->
        <sqf:add node-type="element" target="alt" position="first-child" select="$alt"/>
      </sqf:fix>
    </rule>
    <rule context="xref[@scope = 'external']">
      <assert id="xref-text" test="normalize-space(.)" role="warning" sqf:fix="xref-add-text">A web link says where it goes.</assert>
      <sqf:fix id="xref-add-text">
        <sqf:description><sqf:title>Add link text</sqf:title></sqf:description>
        <sqf:user-entry name="text"><sqf:description><sqf:title>Link text</sqf:title></sqf:description></sqf:user-entry>
        <sqf:add node-type="text" select="$text"/>
      </sqf:fix>
    </rule>
    <rule context="draft-comment">
      <assert id="comment-author" test="@author" role="info" sqf:fix="comment-add-author">A draft comment says who wrote it.</assert>
      <sqf:fix id="comment-add-author">
        <sqf:description><sqf:title>Add the author</sqf:title></sqf:description>
        <sqf:user-entry name="who"><sqf:description><sqf:title>Who wrote the comment?</sqf:title></sqf:description></sqf:user-entry>
        <sqf:add node-type="attribute" target="author" select="$who"/>
      </sqf:fix>
    </rule>
  </pattern>
  <pattern id="reach-outside">
    <rule context="topic/title">
      <assert id="title-shortdesc" test="following-sibling::shortdesc" role="warning" sqf:fix="title-add-shortdesc">A topic has a short description after its title.</assert>
      <sqf:fix id="title-add-shortdesc">
        <sqf:description><sqf:title>Add a short description from the title</sqf:title></sqf:description>
        <sqf:add node-type="element" target="shortdesc" position="after"><sqf:copy-of select="node()"/>.</sqf:add>
      </sqf:fix>
    </rule>
    <rule context="ol/li">
      <report id="ol-one-item" test="count(../li) = 1" role="info" sqf:fix="ol-to-ul">A numbered list has more than one item.</report>
      <sqf:fix id="ol-to-ul">
        <sqf:description><sqf:title>Make it a plain list</sqf:title></sqf:description>
        <sqf:replace match="parent::ol" node-type="element" target="ul"><sqf:copy-of select="node()"/></sqf:replace>
      </sqf:fix>
    </rule>
    <rule context="section/title">
      <assert id="section-id" test="../@id" role="warning" sqf:fix="section-add-id">A section with a title has an id, so it can be linked.</assert>
      <sqf:fix id="section-add-id">
        <sqf:description><sqf:title>Give the section an id from its title</sqf:title></sqf:description>
        <sqf:add match=".." node-type="attribute" target="id" select="lower-case(replace(normalize-space(title), '[^A-Za-z0-9]+', '-'))"/>
      </sqf:fix>
    </rule>
  </pattern>
</schema>
