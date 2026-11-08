// The product roadmap's single content owner. Entries record intent, not delivery.
// Update the existing entry when work ships; do not leave completed repairs pending.
export const roadmap = [
    {
        id: "interface", title: "GUI & usability", summary: "Clearer feedback and controls throughout the interface.",
        items: [
            {title: "More translations", description: "Add carefully reviewed interface translations while keeping model names, controls and help consistent."},
        ],
    },
    {
        id: "workflow", title: "Current workflow improvements", summary: "Build on the image creation and image-to-3D workflows already in use.",
        items: [
            {title: "Better vehicle, prop and creature turnarounds", status: "Evaluate", description: "Revisit the original turnaround recipe and published guidance for each category. Evaluate a single three-quarter starting image where a head-on front/back pair hides important shape. Preserve the successful character approach."},
            {title: "Category-specific view sets", status: "Evaluate", description: "Determine how many views each category needs and which angles help. Investigate a fifth, top-down vehicle view, including extraction, view order, camera information and Pixal3D/TRELLIS input support before adopting it."},
            {title: "Enhance Prompt in image creation", description: "Add an optional language-model prompt enhancement button that preserves the user's idea, reference roles and front/back details. Let the user review the result before generating."},
            {title: "Refinement comparisons", status: "Evaluate", description: "Keep one refinement pass recommended. Compare optional rear-then-front passes, and separately investigate aligning and fusing front/rear refinements. Preserve each result so the user can choose before texturing; extra passes may not improve quality."},
        ],
    },
    {
        id: "upcoming", title: "Upcoming workflows", summary: "Complete the remaining Coming Soon workflows, each with its own clear ownership.",
        items: [
            {title: "Refine and Repair an Existing Mesh", description: "Start with an existing mesh and matching reference images. Provide a dedicated refinement, cleanup, texturing and export workflow without repeating initial mesh generation."},
            {title: "Start with a Video", description: "Investigate selecting useful frames and reconstructing an asset from video, then connect the appropriate finishing and export stages."},
            {title: "PC-Controlled Turntable and Camera Capture", description: "Develop capture around a compatible ComXim Bluetooth turntable. Research camera control, calibration and reconstruction, with webcam support and optional camera-specific integrations."},
            {title: "Action Figure Mode", description: "Use identity and style references with toy or figurine presets, poses and optional bases. Support preset or custom bases, reference images and optional lettering."},
            {title: "Print-service handoff", status: "Evaluate", description: "Research service-specific file requirements, physical print checks, upload APIs and possible referral programs for figure and print exports."},
        ],
    },
    {
        id: "research", title: "Models & tools to evaluate", summary: "Research candidates, not promised integrations. Verify availability, licenses, access requirements and practical hardware needs first.",
        items: [
            {title: "Hunyuan3D 2.1", status: "Evaluate", description: "Compare its initial geometry with Pixal3D/TRELLIS on the same vehicle, prop and character references, including usefulness before Hi3D refinement. Review memory/offloading needs, Windows support, model access and license requirements before choosing an optional backend.", source: "https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1", sourceLabel: "Official project"},
            {title: "SkinTokens / TokenRig", status: "Evaluate", description: "Evaluate automatic skeleton and skin-weight generation on our finished meshes. Assess stylized proportions, deformation quality, skeleton compatibility, hardware needs and licensing before adding a rigging workflow.", source: "https://github.com/VAST-AI-Research/SkinTokens", sourceLabel: "Official project"},
            {title: "Kimodo", status: "Evaluate", description: "Evaluate text-driven character motion and preset animations after rigging. Check skeleton mapping, foot contact, body intersections, export formats, memory offloading and checkpoint licenses.", source: "https://github.com/nv-tlabs/kimodo", sourceLabel: "Official project"},
            {title: "UltraTex", status: "Evaluate", description: "Investigate texturing existing geometry and the reported 2K albedo and metallic/roughness outputs. Compare seams, material accuracy and alignment against our current texture workflow.", source: "https://www.reddit.com/r/TopologyAI/comments/1wzlljg/new_opensource_ai_texturing_for_3d_models_at_2k/", sourceLabel: "Research lead"},
            {title: "UniMate", status: "Evaluate", description: "Identify the exact project and evaluate its rigging or animation capabilities, required mesh/skeleton inputs, exports and usefulness for Foundry assets."},
            {title: "SAM 3D Body", status: "Evaluate", description: "Evaluate human reconstruction, clothed and stylized subjects, and compatibility with our character workflow. Establish its actual scope rather than assuming general object reconstruction or automatic animation readiness."},
            {title: "Kimi procedural 3D scripting", status: "Evaluate", description: "Verify the supplied model and release claims, then investigate editable, code-driven assets in Blender and game engines. Compare actual available capabilities with our existing agent and MCP approach; model names, dates and weight availability remain unverified.", source: "https://x.com/Kimi_Moonshot/status/2113680701770068067", sourceLabel: "Unverified research lead"},
            {title: "Strand-based Groom export", status: "Evaluate", description: "Research creating and exporting suitable curves as Alembic for Unreal's Groom system. Keep this separate from ordinary triangle/quad mesh and FBX exports."},
        ],
    },
    {
        id: "integration", title: "Architecture & integration", summary: "Shared requirements for future workflow additions and releases.",
        items: [
            {title: "Independent workflows, shared services", description: "Give each workflow a dedicated graph section and cohesive code ownership. Reuse shared model, resource, gallery and export services without creating one tangled graph."},
            {title: "Memory profiles that affect the workflow", description: "Keep the working default profile, including the tested Splat & Solid path. Qualify additional hardware profiles across each workflow later, with explicit user choices taking precedence and clear memory recommendations."},
            {title: "MCP and export documentation parity", description: "Expose new workflow choices to agents and keep package README contents, file descriptions, model provenance and license links aligned with the outputs actually selected."},
            {title: "Portable updates and first-use preparation", description: "Trace dependencies for every runtime when adding features. Check access and prepare all selected workflow resources before generation, download models only on first use, and keep ComfyUI and Pinokio releases consistent."},
        ],
    },
];
