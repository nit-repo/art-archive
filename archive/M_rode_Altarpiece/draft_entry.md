Here's a thinking process:

1.  **Analyze User Request:**
   - User wants me to build a permanent archive entry for an artwork called "Mérode Altarpiece"
   - I must follow strict rules: only state facts from provided sources, cite with `[source: <source_id>]`, if info missing say "Not available in retrieved sources — needs manual research", distinguish canonical facts vs traditions/debates vs synthesis, never invent info, clear plain prose, specific Markdown structure.

2.  **Analyze Provided Sources:**
   Let me go through each source carefully:

   - `wikidata_001`: 
     - Creator: some genid (not useful for human-readable attribution directly, but implies Wikidata link)
     - Inception date: 1500-01-01T00:00:00Z (this seems like a default/wikidata standard date, but I need to check other sources)
     - Medium: oil paint
     - Current location: The Cloisters
     - Movement: Early Netherlandish painting

   - `wikipedia_summary_001`:
     - The Mérode Altarpiece is an oil on oak panel triptych
     - Now in The Cloisters in New York
     - Unsigned and undated
     - Attributed to Early Netherlandish painter Robert Campin and an assistant
     - Three panels: left = donors kneeling in prayer in a garden; center = Annunciation to Mary in contemporary domestic setting; right = Saint Joseph carpenter with tools
     - Religious symbolism: lily and fountain, Holy Spirit = rays of light from central panel's left-hand window

   - `wikipedia_full_001`:
     - Also called Annunciation Triptych
     - Oil on oak panel triptych
     - Now in The Cloisters in New York
     - Unsigned and undated
     - Attributed to Early Netherlandish painter Robert Campin and an assistant
     - Three panels left to right: donors kneeling in prayer in a garden; Annunciation to Mary in contemporary domestic setting; Saint Joseph carpenter with tools
     - Religious symbolism: lily and fountain (symbolising purity of Mary); Holy Spirit = rays of light from central panel's left-hand window
     - Central panel completed after 1422, likely between 1425 and 1428, thought by a member of Campin's workshop
     - Earlier version now in Brussels, may be Campin's original panel
     - Outer wing panels are later additions by a workshop member, probably on request by the donor who sought to elevate the central panel to a triptych and place himself in the pictorial space
     - Outer wings contain views of the city of Liège, in today's Belgium
     - Triptych is a founding and important work in then emerging late Gothic...

   - `met_001`:
     - Title: The Annunciation
     - Artist: Hans Memling
     - Date: ca. 1465–70
     - Medium: Oil on wood
     - Dimensions: 73 1/4 x 45 1/4 in. (186.1 x 114.9 cm)
     - Department: European Paintings
     - Credit line: Gift of J. Pierpont Morgan, 1917
     - Image URL
     - Note: This seems to be a different artwork (also called "The Annunciation" but by Hans Memling, not the Mérode Altarpiece). I need to be careful not to conflate this with the Mérode Altarpiece. The query is "Mérode Altarpiece", and this source is about a different work. I should not use this to claim facts about the Mérode Altarpiece unless it's clearly linked. Looking at the raw_text, it's just "Title: The Annunciation; Artist: Hans Memling..." It's a different piece. I'll note that it's not relevant or I'll exclude it if it doesn't pertain to the Mérode Altarpiece. But the rules say "only state a fact if it appears in one of these snippets" and "if the provided sources do not contain information for a section, write exactly: 'Not available in retrieved sources — needs manual research.'" I need to check if any fact about the Mérode Altarpiece comes from met_001. It doesn't seem to; it's a different artwork. I'll treat it as not applicable, or perhaps mention it's a different work. But the instructions say to only state facts from sources. I'll not include met_001 facts in the entry about Mérode Altarpiece, as they're about a different artwork. However, the source bundle is for "Mérode Altarpiece", but met_001 is clearly a different piece. I'll be careful.

   Let me re-examine: The `artwork_query` is "Mérode Altarpiece". The sources include `met_001` which is about "The Annunciation" by Hans Memling. This might be a distractor or related, but it's not the Mérode Altarpiece. I must not invent connections. I'll only use facts from sources that discuss the Mérode Altarpiece. The `met_001` source does not mention "Mérode Altarpiece" in its raw_text, so I won't cite it for facts about this artwork. I'll either omit it or note it's not relevant. The rules say "Only state a fact if it appears in one of these snippets." So if a fact isn't in a source that's about the artwork, I can't state it. I'll focus on the three Wikipedia/Wikidata sources that are clearly about the Mérode Altarpiece.

   Now, let's extract facts that are directly stated and attributed to specific sources:

   - **Artwork name**: Mérode Altarpiece (implied from query, but sources mention it)
   - **Medium**: oil on oak panel (wikipedia_summary_001, wikipedia_full_001)
   - **Format**: triptych (wikipedia_summary_001, wikipedia_full_001)
   - **Current location**: The Cloisters (wikidata_001, wikipedia_summary_001, wikipedia_full_001)
   - **Attribution**: Robert Campin and an assistant (wikipedia_summary_001, wikipedia_full_001)
   - **Unsigned and undated**: wikipedia_summary_001, wikipedia_full_001
   - **Panels description**:
     - Left: donors kneeling in prayer in a garden (wikipedia_summary_001, wikipedia_full_001)
     - Center: Annunciation to Mary in contemporary domestic setting (wikipedia_summary_001, wikipedia_full_001)
     - Right: Saint Joseph, carpenter with tools (wikipedia_summary_001, wikipedia_full_001)
   - **Symbolism**: lily and fountain (symbolising purity of Mary) (wikipedia_full_001); Holy Spirit represented by rays of light from central panel's left-hand window (wikipedia_summary_001, wikipedia_full_001)
   - **Dating/Completion**: Central panel completed after 1422, likely between 1425 and 1428, thought by a member of Campin's workshop (wikipedia_full_001)
   - **Earlier version**: Earlier version now in Brussels, may be Campin's original panel (wikipedia_full_001)
   - **Outer wing panels**: Later additions by a workshop member, probably on request by the donor who sought to elevate the central panel to a triptych and place himself in the pictorial space (wikipedia_full_001)
   - **Outer wings contain**: Views of the city of Liège, in today's Belgium (wikipedia_full_001)
   - **Movement/Style**: Early Netherlandish painting (wikidata_001)
   - **Inception date**: wikidata_001 says 1500-01-01T00:00:00Z, but wikipedia_full_001 says central panel completed after 1422, likely 1425-1428. There's a discrepancy. I need to handle this carefully. The wikidate date might be a default or erroneous. I should not invent; I can note what sources say. Rule 3: "If the provided sources do not contain information for a section, write exactly: 'Not available in retrieved sources — needs manual research.'" But here we have conflicting info. I need to state facts with citations, and perhaps note the disagreement in section 5. I'll be precise: I'll cite what each source says, and in section 5 discuss the debate/disagreement.

   - **met_001**: As noted, it's a different artwork. I will not use it for Mérode Altarpiece facts. I could mention it's a separate work, but the query is specifically for Mérode Altarpiece archive entry. I'll ignore it for the main entry, or perhaps add a note if needed, but better to stick to sources that discuss the Mérode Altarpiece. The rules say "Only state a fact if it appears in one of these snippets." It does appear, but it's about a different artwork. I need to decide. I think the safest is to not include met_001 facts in the entry about Mérode Altarpiece, as they're not about this artwork. I'll treat it as "not available in retrieved sources" for sections where met_001 would be the only source, but since other sources cover it, I won't invoke that clause. I'll just not include met_001 citations.

   Now, let's structure the entry per the required format:

   # [Artwork Name] -> Mérode Altarpiece

   ## 1. Basic Information
   - Artist: Robert Campin and an assistant (attributed) — I need to cite. From wikipedia_summary_001 and wikipedia_full_001. I'll cite both or use one. I'll use [source: wikipedia_summary_001] and [source: wikipedia_full_001] perhaps. But rule says "for every factual claim you make, append a citation tag in this exact format: [source: <source_id>]" — I can have multiple citations per claim? It says "append a citation tag", singular, but I can use multiple if needed, or pick the most appropriate. I'll try to cite the source that states it. I'll use [source: wikipedia_full_001] for attribution, as it's detailed.
   - Date: Not available (unsigned and undated per sources). But wikidata_001 says 1500-01-01, wikipedia_full_001 says central panel after 1422, likely 1425-1428. I need to handle this carefully. I'll state "unsigned and undated" as per sources, and note the attributed dating in section 5. For basic info, I'll say "Attributed to Robert Campin and an assistant; unsigned and undated, though central panel likely completed c. 1425–1428" but I must cite. Let's see: I can state the "unsigned and undated" fact with citation, and the dating with citation. I'll be precise.
   - Medium: oil on oak panel — cite [source: wikipedia_summary_001] or [source: wikipedia_full_001]
   - Dimensions: Not mentioned in the Mérode-specific sources! I check: wikipedia_summary_001 no dimensions. wikipedia_full_001 no dimensions. wikidata_001 no dimensions. met_001 has dimensions but for a different artwork. So dimensions are not available in retrieved sources for this artwork. I'll have to write "Not available in retrieved sources — needs manual research." for that subfield, or handle per section. The section says: "(Artist, date, medium, dimensions, current location — each cited)". If dimensions not in sources, I need to say exactly "Not available in retrieved sources — needs manual research." per rule 3. But rule 3 says "If the provided sources do not contain information for a section, write exactly: 'Not available in retrieved sources — needs manual research.'" It's a bit ambiguous: does it apply to the whole section or per fact? The instruction says: "If the provided sources do not contain information for a section, write exactly: 'Not available in retrieved sources — needs manual research.' Do not guess or infer." I think it means if a section can't be filled, but the section has multiple sub-items. I'll interpret it as: for each factual claim, if not in sources, don't state it, and if a whole sub-section lacks info, maybe write that phrase. But the structure requires those sub-items. I'll try to cite what's available, and for dimensions, since it's not in any source about the Mérode Altarpiece, I'll write "Not available in retrieved sources — needs manual research." as a line item. But rule 3 says "If the provided sources do not contain information for a section, write exactly: 'Not available in retrieved sources — needs manual research.'" I'll apply it to the dimensions part. Let's read carefully: "4. Explicitly distinguish: (a) canonical/primary facts stated directly in a source, (b) traditions or interpretations the source itself frames as debated or attributed, (c) your own synthesis connecting two sourced facts (mark this clearly as 'Synthesis:')." and "3. If the provided sources do not contain information for a section, write exactly: 'Not available in retrieved sources — needs manual research.' Do not guess or infer." I think this means if I'm asked to produce a section and the sources don't have it, I write that exact phrase. But here the section is "Basic Information" with sub-items. I'll try to provide what I can, and for dimensions, I'll include a line saying "Dimensions: Not available in retrieved sources — needs manual research." I'll also cite that it's not found. But to be safe, I'll just omit the dimension value and perhaps add a note, but the rules say exactly that phrase. I'll include it as a line item with that exact phrase, and maybe cite that sources don't provide it. Actually, the phrase is to be written exactly when a section lacks info. I'll treat the missing dimension as: "Dimensions: Not available in retrieved sources — needs manual research." I'll also maybe add a citation note, but the phrase must be exact. I'll do that.

   Let's list Basic Information items and what sources say:
   - Artist: Attributed to Robert Campin and an assistant. I'll cite [source: wikipedia_full_001] (or wikipedia_summary_001). I'll use [source: wikipedia_full_001].
   - Date: "unsigned and undated" per sources. I'll state that, and also note the likely dating c. 1425–1428 from wikipedia_full_001, but that's a scholarly note. For Basic Info, I'll state "unsigned and undated" with citation. I can also mention the dating in section 5. I need to be careful not to mix. I'll state date as "unsigned and undated" [source: wikipedia_summary_001]. Then in section 5, I'll discuss the dating debate.
   - Medium: oil on oak panel [source: wikipedia_summary_001] or [source: wikipedia_full_001].
   - Current location: The Cloisters [source: wikidata_001] or [source: wikipedia_summary_001]. I'll cite [source: wikidata_001] or [source: wikipedia_summary_001]. I'll use [source: wikidata_001] for location, as it's explicit.
   - Dimensions: Not available.

   Actually, let's re-read the required format for section 1: "(Artist, date, medium, dimensions, current location — each cited)". So I need to list each, with citations. I'll do:

   **Artist**: Attributed to Robert Campin and an assistant [source: wikipedia_full_001].
   **Date**: unsigned and undated [source: wikipedia_summary_001]; central panel likely completed c. 1425–1428 (see Scholarly Notes) — but I can't state the likely dating in section 1 if I'm only citing facts. Rule 2: "For every factual claim you make, append a citation tag". The "unsigned and undated" is a factual claim from sources. The "likely completed c. 1425–1428" is also a claim from wikipedia_full_001, but it's a scholarly interpretation. I could include it with citation, but then section 5 might be redundant. I'll keep section 1 strict: only state what sources directly say. Wikipedia_full_001 says "It is unsigned and undated, but attributed to Early Netherlandish painter Robert Campin and an assistant." and "The central panel was completed after 1422, likely between 1425 and 1428, it is thought by a member of Campin's workshop." Both are stated as facts in the source. I can cite both. I'll state date as "unsigned and undated, though the central panel is thought to have been completed c. 1425–1428" but I need to cite the "thought" part. I'll just state what's directly said: "unsigned and undated" [source: wikipedia_summary_001], and then in section 5 discuss the dating. To keep it clean, I'll state date as "unsigned and undated" [source: wikipedia_summary_001], and note that wikipedia_full_001 provides a likely range. But the format wants date cited. I'll include the likely range with citation: "unsigned and undated, but central panel likely completed c. 1425–1428 [source: wikipedia_full_001]". That's a factual claim from the source. I'll do that.

   **Medium**: oil on oak panel [source: wikipedia_summary_001].

   **Dimensions**: Not available in retrieved sources — needs manual research. [I'll write