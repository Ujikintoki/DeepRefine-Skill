---
description: DeepRefine Wiki Adapter — import, retrieve, refresh, and update LLM-Wiki knowledge graphs (Obsidian, GitHub Wiki, etc.)
---

# /deeprefine-wiki

<command-instruction>
Use the `skill` tool to load the DeepRefine skill:

skill(name="deeprefine")

Then execute the Wiki Adapter workflow. This command is for LLM-Wiki knowledge graphs (Obsidian vaults, GitHub Wikis, etc.) instead of code knowledge graphs.

**Wiki-specific retrieval methods**: `wiki_search` and `k_hop_expansion` (instead of `graphify_query`)

**Write-back**: uses wiki link syntax (`[[wikilinks]]` or `[text](url)`)

**Workflow**:
1. Import wiki: `deeprefine wiki import --wiki-dir <path>`
2. Retrieve from wiki: `deeprefine wiki retrieve --query <text>`
3. Refresh wiki: `deeprefine wiki refresh --graph <path> --wiki-dir <path>`
4. Update wiki: `deeprefine wiki update --graph <path> --wiki-dir <path>`

<user-request>$ARGUMENTS</user-request>
</command-instruction>
