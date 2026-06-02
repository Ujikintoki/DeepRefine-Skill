"""DeepRefine Reafiner prompts — verbatim from autorefiner deeprefine_prompt.py."""

REAFINER_JUDGEMENT_SYSTEM = """
As an advanced judgement assistant, your task is to judge whether the given question is answerable based on the provided KG context.

Evaluate whether the given question is answerable based on the provided KG context. Output your judgment in the following format:
<judge>Yes</judge> or <judge>No</judge>

**Important:** You must think carefully about the question and the KG context before making your judgment. And output your judgment result directly in the specified format.
"""

REAFINER_JUDGEMENT_USER = """
Question: {question}
Knowledge Graph (KG) context: {triples_string}
"""

REAFINER_ERROR_ABDUCTION_SYSTEM = """
As an advanced error abduction assistant, your task is to analyze the error reasons based on the given interaction history.

Analyze the reasons of the unanswerable questions based on the given interaction history from the incompleteness, incorrectness, and redundancy perspectives. Output your analysis in the following format:
<abduction>...</abduction>

**Important:** You must think carefully about the interaction history before making your analysis. And output your analysis result directly in the specified format.
"""

REAFINER_ERROR_ABDUCTION_USER = """
Interaction history: {interaction_history}
"""

REAFINER_KG_REFINEMENT_ACTION_SYSTEM = """
As an advanced knowledge graph refinement assistant, your task is to generate a series of actions (**within 10 actions**) to refine the given KG to make it more suitable for answering the given question.

Based on the given KG and the analysed error reasons, refine the given KG to make it more easily for retrieval and answering the given question. You have the following three types of actions to conduct:

- insert_edge(subject, relation, object): Insert a new edge into the KG to complete the missing information.
- delete_edge(subject, relation, object): Delete an edge from the KG to remove the redundant information or conflicting information.
- replace_node(old_entity, new_entity): Replace an entity in the KG to correct the errors or deal with disambiguation.

Output a series of actions (**within 10 actions**) in the following format:
<refinement>insert_edge("...", "...", "...")|delete_edge("...", "...", "...")|replace_node("...", "...")|...</refinement>

**Important:** You must think carefully about the given KG and the analysed error reasons before making your refinement. DO NOT DELETE ANY IRRELEVANT TRIPLES FROM THE ORIGINAL KG. TRY TO KEEP THE ORIGINAL KG AS MUCH AS POSSIBLE. DO NOT GENERATE TOO MANY ACTIONS. And output your refinement result directly in the specified format.
"""

REAFINER_KG_REFINEMENT_ACTION_USER = """
Original Text: {original_text}
KG: {triples_string}
Question: {question}
Error reasons: {error_reasons}
"""

MAX_HOPS_DEFAULT = 4
HISTORY_HORIZON_DEFAULT = 4
INCREMENT_HOP_DEFAULT = 1
BASE_TOP_K_DEFAULT = 10
MAX_TRIPLE_NUM_BY_STEP = [5, 10, 15, 20]
