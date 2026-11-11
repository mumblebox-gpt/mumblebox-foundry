# Chinese editorial review

Date: 2026-11-10. Scope: every non-service_ value in the parent-authored English/Chinese runtime catalogs for ccore, splat, hair, images and garment, plus both repository-root READMEs. Runtime files were not edited.

## Coverage and result

Read all 521 non-service entries: ccore 70, splat 90, hair 112, images 124, garment 125. A mechanical comparison found no missing Chinese values or named-placeholder mismatches in this review snapshot. Model/researcher names and technical formats were preserved; two messages unnecessarily replaced the literal README filename with a generic description, listed below.

Overall the Chinese is clear and modern. The important corrections concern a list mislabeled as a count, an image mislabeled as a chart, and a target avatar mistranslated as a tool. This is bilingual source/editorial review, not native-speaker acceptance, visual layout proof or installed runtime proof.

## Corrections to apply

Keys below are domain-qualified. Keep every named placeholder unchanged.

| Key | Finding | Proposed Chinese replacement |
|---|---|---|
| garment.test_skin_weights_saved_sampled_poses | The placeholder is not a pose count. controller.js supplies a list of pose names and clipping results. The current “已采样的姿势数为” misrepresents that list. | 测试用蒙皮权重已保存。采样姿势检查 · {value1} |
| hair.hairdeck_processing_sheet | “处理图表” means a chart/graph. This label describes the preprocess image display, not the node graph. | HairDeck 预处理拼图 |
| hair.static_glb_is_unrigged_vrm_contains_skinning_and_spring_data_inspect_it_with | “目标模型工具” changes avatar into a tool and weakens the instruction to check the intended character/runtime. | 静态 GLB 不含绑定。VRM 包含蒙皮和弹簧骨数据，请结合目标角色模型及运行环境进行检查。预测骨链数可能与实际保留的已绑定骨链数不同。 |
| ccore.the_glb_is_the_asset_you_just_reviewed_the_zip_adds_a_readme_model_credits_a | Retain the exact README file identifier. “文件清单” is clearer than “文件目录” for the catalog. | GLB 就是刚才预览的资产。ZIP 还包含 README、模型致谢和文件清单。 |
| hair.choose_the_files_to_deliver_the_package_includes_an_accurate_readme_measurem | Retain README explicitly rather than replacing it with “说明”. | 选择需要导出的文件。资产包会附上与实际内容相符的 README、测量数据、来源记录和资源许可证。 |
| ccore.continue_to_downloads | “继续下载” suggests resuming/starting a transfer, but this control only navigates to the download page. | 前往下载页 |
| garment.continue_to_export | Likewise this control opens the export page; it does not continue an export job. | 前往导出页 |
| splat.visual_detail_from_idol_separate_companion_geometry | The current “Idol…同时提供” can attribute Foundry’s downstream cleaned companion to Idol. Keep the two responsibilities distinct. | Idol 提供丰富的外观细节，另配独立的几何网格。 |

Evidence: [garment/controller.js](../../../comfyui_asset_workshop/web/foundry/garment/controller.js), especially the pose_checks mapping at line 411 and navigation at line 465; [hair/review.js](../../../comfyui_asset_workshop/web/foundry/hair/review.js), whose display labels associate the processing sheet with preprocess; [ccore/controller.js](../../../comfyui_asset_workshop/web/foundry/ccore/controller.js), download-page navigation at line 430.

## Small wording improvements

These are editorial refinements rather than confirmed behavior defects.

| Key | Proposed replacement | Reason |
|---|---|---|
| ccore.most_room_default | 最大预算（默认） | Preserves “Most”; “充足预算” only says sufficient. |
| ccore.uses_less_gpu_memory_and_leaves_more_room_for_longer_generations | 占用更少的 GPU 显存，为生成更长的输出留出更多空间。 | Keeps token/output length distinct from simply taking longer. |
| images.the_model_is_downloading_on_first_use_this_may_take_some_time_but_only_happe | 正在下载首次使用所需的模型。可能需要一些时间，但每个模型只需下载一次。 | Avoids the awkward “首次使用此模型时正在下载”. |

Do not replace other acceptable choices just to match the research draft’s vocabulary. For example, 图片/图像, 方案/变体 and 弹簧骨/弹簧骨骼 are valid choices if used consistently. The reviewed numerical limits, model/author credits, hair-card-versus-Groom warning, static-GLB-versus-VRM distinction, non-exportable head-turn preview warning, geometry/collision limitation and experimental garment caveats retain their English meanings.

## Adjacent untranslated fragments found during context checks

These are outside the JSON-value wording corrections but directly affect the reviewed garment status:

- garment/controller.js:411 still composes each pose detail with the raw English suffix “clipping”. Localize the complete per-pose message, with pose name and count as arguments, before inserting it into garment.test_skin_weights_saved_sampled_poses. Do not solve this by translating pose IDs.
- garment/controller.js:408 still contains the uncatalogued help “Red marks show vertices inside the body. Also look for gaps where the fabric hangs away from it.” Proposed copy: 红色标记表示位于身体内部的顶点。也请检查布料悬离身体形成的空隙。

## Root README pair

Both files preserve the same nine-workflow scope, practical output caveats, optional quads, experimental garments, local generation, separate interface/prompt language, selected-resource preparation and model-license separation. Neither translation adds a print-certification, animation-readiness or minimum-hardware guarantee.

Apply these localized corrections in README.zh-CN.md:

| Location | Correction |
|---|---|
| MCP/skill introduction, line 18 | Replace “理解输入要求和显存限制” with “理解输入要求及内存、显存限制”. English “memory limits” includes system RAM as well as GPU VRAM. |
| Splat & Solid table row, line 30 | Use “Sperid Labs 的 Idol 生成细致的高斯泼溅；Foundry 另行提供清理后的配套网格，并可选用 Hi3D 细化。” This avoids the same ownership ambiguity as the UI sentence. |
| CCORE Text table row, line 31 | Retain optionality: “12 个可编辑示例、可选的本地 Qwen 描述增强、3D 预览和 GLB 导出”. |
| HairDeck table row, line 33 | Replace “处理图表” with “预处理拼图”. |
| Package paragraph, line 56 | Replace generic “说明文档” with “README” and preferably “私人的源图片” with “私有源图片”. |
| Language paragraph, line 60 | Optional fluency improvement: replace “通过本地文本目录直接更新界面” with “使用本地语言资源直接更新界面”. The existing phrase can sound like a filesystem-directory operation. |

The update/agent guidance is accurate and consistent in both languages: updating the app refreshes its bundled skill; an independently copied skill needs refreshing separately; the agent checks version, protocol/compatibility, capabilities and update information; explanations use the user’s language; live capabilities govern supported controls. This was checked against [AGENT-SETUP.md](../../AGENT-SETUP.md), the actual [bundled skill](../../../comfyui_asset_workshop/skills/mumblebox-assets/SKILL.md) and its [compatibility record](../../../comfyui_asset_workshop/skills/mumblebox-assets/compatibility.json). No correction is needed to that guidance.

Source READMEs: [English](../../../README.md), [Simplified Chinese](../../../README.zh-CN.md). Runtime language-switching/state-preservation claims still require the parent’s behavioral proof; wording parity is not that proof.


## Final bounded CCORE and package review — 2026-11-10

Reviewed the new bilingual English-guidance, translation and enhancement controls, all 12 full preset descriptions and their category/name fields, and the added CCORE paragraph in both root READMEs. Scope remains English and Simplified Chinese; French and other languages are deferred.

No new material semantic drift was found. All 12 runtime Chinese presets match the reviewed full drafts. Counts, spatial relationships, materials, exclusions and static-object instructions remain intact, including the four sofa legs, two side drawers, three microscope objectives, six bolts per valve flange, four handwheel spokes, four lantern ribs, two crate latches, three crate ribs, four rover wheels, two boat benches and two oars. The unusual source comparison between sofa back height and arm length remains literal rather than silently reinterpreted.

All 152 non-service CCORE catalog entries have Chinese values and matching named placeholders. The controls and README paragraphs clearly distinguish an explicit translation action from creative description enhancement, and request review before generation. Localized built-in presets are Brian’s explicit exception; these words do not authorize automatic rewriting of arbitrary user prompts. This is editorial/source evidence only.

Optional fluency refinements, without a change of meaning:

| Exact key/location | Suggested adjustment |
|---|---|
| ccore.stop_description_task | “停止描述助手” is clearer than “停止助手”, matching the preparation/stopping status wording. |
| ccore.preset_sofa_prompt | Replace “这条连续的靠背和两侧向外舒展的扶手” with “连续延伸的靠背和两侧向外舒展的扶手”. |
| ccore.preset_crate_prompt | Replace “竖向棱角切角” with “竖向棱角作切角处理”. |
| README.zh-CN.md, final CCORE paragraph | Move the paragraph beginning “CCORE 作者建议使用英文提示词生成资产” into “语言与阅读设置”, after the interface/generation-language paragraph, matching the English README. Content is faithful; current placement after the footer is harder to discover. |

Prepared all 18 controlled package captions in [zh-CN-package-content.json](zh-CN-package-content.json). Keys and placeholders are preserved. The descriptions retain the distinction between authoring polygon faces and triangulated runtime derivatives, preserve GLB/SHA-256 identifiers, and explicitly keep physical-fabrication validation and enhanced-view camera adherence subject to separate checks. No runtime files were edited in this review.
