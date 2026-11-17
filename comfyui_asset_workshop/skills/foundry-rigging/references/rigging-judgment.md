# Placement and deformation judgment

Read for fitting, detailed anatomy or diagnosing a bad bend. These are decision aids, not a substitute for visual inspection or mesh-specific anatomy.

## Diagnose before changing

| Observation | Inspect first | Appropriate response |
|---|---|---|
| Bent limb pivots away from its physical joint | Bone head, parent chain, side view | Correct the pivot; preserve child placement deliberately |
| Finger curls sideways or twists | Local rest axes/roll, thumb orientation, pose mapping | Correct bend orientation or the pose mapping; do not move a well-placed pivot just to hide it |
| Correct pivot but nearby torso/opposite finger moves | Weight influence heat map and region selection | Fix leakage with bounded weight edits, normalize unlocked influences and retest |
| Joint collapses despite plausible weights | Topology around bend, linear-skinning limits, shape/volume | Compare placement and weights; disclose need for a corrective or topology work if necessary |
| Metal plates stretch like rubber | Rigid region boundaries, mixed influences | Propose/assign rigid weighting to the appropriate bone; preserve flexible hinges |
| Open head, missing back, fused fingers | Rest mesh from multiple angles | Identify geometry limitation. Do not call more bones or smoothing a mesh repair |
| Auto-fit omits an appendage | Full raw prediction, adapter losses, anatomy | Preserve useful structure and add a supported chain; do not assume the model is incapable before checking conversion |
| New bones vanish after binding | Conditioning receipt and output hierarchy | Reject silent replacement; retain the edited rig and select a verified binder |

## Place pivots in three dimensions

Use the source asset's coordinate frame and units. Bone heads represent rotation pivots, not visible decorative joints or silhouette points. Check front plus side/oblique views; opaque armor can hide the true pivot, so state uncertainty instead of assigning false confidence.

For limbs, use the socket/hinge center and a coherent bend plane. A slight pre-bend can help IK resolve direction, but do not impose one on a straight rigid mechanism without understanding its motion. Check the chain's local axes. Mirroring requires a correct symmetry plane and corresponding parts; asymmetric poses and proportions may need independent fitting.

Use the [spatial inspection guide](spatial-inspection.md) for evidence about location and depth. For a weight stroke, select the intended bone and use actual visible surface points.

## Hands and feet

Count the actual fingers and inspect separation before choosing a template. Preserve individual predicted branches. Identify thumb base/opposition separately from the four fingers; a thumb is not just a sideways index finger. Review knuckles, intermediate joints and terminal tips from palm/back/side views. Do not treat the fingertip marker as another knuckle.

Test one finger at a time, then a combined curl and spread. Watch adjacent-finger motion, webbing distortion and thumb twisting. A full fist may be inappropriate for a stylized rigid hand; test the user's intended motion. Feet may need a toe-base pivot or separate toes depending on anatomy and purpose. Do not add joints for detail the geometry cannot represent usefully.

## Tails, wings and custom parts

Tail: attach at the anatomical base, follow the volume's centerline, use enough segments for the desired curvature, and inspect side-to-side plus up/down sweeps. Avoid copying unrelated humanoid leg weights onto it.

Wing: determine bird-like or bat-like structure and visible joints. Shoulder/elbow/wrist motion, elongated digits, membrane and feather support are different responsibilities. A generic chain can be a starting structure but does not prove correct folding or membrane deformation.

Extra limbs/custom chains: confirm attachment and hierarchy, stable identity, bend plane and which geometry each should influence. Do not mirror automatically across an unverified plane or assume bilateral anatomy. Decorative antennae, horns or clothing may be rigid or deforming depending on the requested motion.

## Weights and movement

Inspect the selected bone's influence on the intended region and nearby disconnected pieces. Keep weights finite, nonnegative and normalized under the target's influence limit. Preserve locked groups; report when they make normalization impossible. A four-influence cap is an export/performance choice, not a universal artistic rule.

Use restrained local smoothing where it improves a transition. Fixed 50/50 weights or a universal falloff width do not fit every mesh. Judge volume, sliding, leakage and rigid-part behavior in motion. Never smooth the whole mesh to fix one finger.

Rest skeleton, deform skeleton and animator controls are different. Do not weight to a nondeforming IK handle. Animation retargeting needs verified semantic correspondence; matching names alone is insufficient. Test actual baked/exported movement when constraints cannot travel in the output format.

## Review standard

Start with rest, then purposeful movements for the asset: elbow bend, raised arms, knee/hip flexion, finger curl/spread, tail sweep or wing fold. Use conservative and more demanding angles without violating the design's intended range. Compare the same view/pose before and after. Record what was observed and which areas remain untested; a static attractive render does not prove a usable rig.

References for maintainers: [Blender bone roll](https://docs.blender.org/manual/en/latest/animation/armatures/bones/editing/bone_roll.html), [weight options](https://docs.blender.org/manual/en/latest/sculpt_paint/weight_paint/tool_settings/options.html), [AccuRIG hand inspection](https://manual.reallusion.com/ActorCore-AccuRIG-1/Content/ENU/1.1/07-Hand-Rig/Setting-and-Mirroring-Joints.htm). The workflow above is original Foundry guidance, not copied third-party operating instructions.
