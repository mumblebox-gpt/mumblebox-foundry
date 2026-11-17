---
name: foundry-rigging
description: Use when working in Mumblebox Foundry's rigging wizard or MCP on automatic rigs, joints, chains, hands, appendages, skin weights, deformation checks or rig export.
---

# Foundry rigging

Read the running Foundry's capabilities and current rig. Confirm the selected source variant and hash, run ID, revision, pose, binding state and intended movement. Work in the user's visible wizard.

## Start from the user's actual asset and intent

Retain the full automatic rig, unknown bones, source mesh and user edits. Treat Stop agent editing as a hard boundary. Report the stopped state and wait for the person to resume. Never retry a blocked edit through another route or app.

| If you need to… | Read |
| --- | --- |
| Choose a pivot, diagnose a bad bend or assess weights | [Rigging judgment](references/rigging-judgment.md) |
| Interpret a view, depth span, landmark or local frame | [Spatial inspection](references/spatial-inspection.md) |
| Use MCP to fit, preview, apply, recover, bind, test or export | [MCP workflow](references/mcp-workflow.md) |

## Work in a visual correction loop

1. Frame the affected region and inspect it from two useful angles. Identify the likely cause of the problem.
2. Choose the smallest supported correction and preview related edits together. Respect pins, asymmetry and the person's current drag.
3. Apply with the current revision, then inspect the same region again. Rebind when the current binding is stale.
4. Test the intended movement and compare nearby parts. Undo or refine if it worsens. Report what moved and where uncertainty remains.

## Completion

Inspect relevant deformation, check the reopened state and verify the exact export in Blender when required. Report any missing operation or untested movement. Leave the person's model visible in the app.
