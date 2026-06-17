# DeepRefine Skill for Gemini CLI

DeepRefine-Skill can be installed as a Gemini CLI extension. This adds Gemini slash commands for the existing agent-native DeepRefine workflow while keeping Cursor support unchanged.

## Prerequisites

```bash
pip install -e /path/to/DeepRefine-Skill
node -v   # Gemini CLI requires Node.js 20+
gemini --version
```

## Recommended development install

From the DeepRefine-Skill repository root:

```bash
deeprefine gemini link
# equivalent to: gemini extensions link .
```

Restart Gemini CLI after linking:

```bash
gemini
```

Then verify inside Gemini CLI:

```text
/extensions list
/commands list
```

You should see the `deeprefine-skill` extension and these commands:

```text
/deeprefine
/deeprefine:review
/deeprefine:apply
```

## Install a copied extension

If you do not want to link the working tree:

```bash
deeprefine gemini install
# equivalent to: gemini extensions install <bundled-extension-template>
```

Restart Gemini CLI afterwards.

## Manual fallback

If the official Gemini extension manager is unavailable, copy the bundled template:

```bash
deeprefine gemini install --copy-only
```

This places files under:

```text
~/.gemini/extensions/deeprefine-skill/
```

Prefer `deeprefine gemini link` or `deeprefine gemini install` because they use Gemini CLI's official extension manager and are more likely to appear in `/extensions list`.

## Usage

Default pending-query workflow:

```text
/deeprefine
```

Read-only review:

```text
/deeprefine:review "How does the training pipeline work from data loading to model output?"
```

Validated apply workflow:

```text
/deeprefine:apply "Apply the validated refinement for the missing train_epoch relation."
```

## Notes

- Gemini CLI authentication is separate from DeepRefine installation.
- If `/extensions list` shows no extension, exit Gemini CLI, run `deeprefine gemini link`, and restart Gemini CLI.
- `/deeprefine` expects a project with `graphify-out/graph.json`; in this repository itself it may correctly report that Graphify outputs are missing.
