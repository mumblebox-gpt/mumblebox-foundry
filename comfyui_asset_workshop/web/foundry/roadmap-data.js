import {msg} from "./i18n.js";
// The product roadmap's single content owner. Entries record intent, not delivery.
// Update the existing entry when work ships; do not leave completed repairs pending.
export const roadmap = [
    {
        id: "interface", title: msg("common.gui_usability"), summary: msg("common.clearer_feedback_and_controls_throughout_the_interface"),
        items: [
            {title: msg("common.did_you_know_tips_during_busy_stages"), status: "Planned", description: msg("common.rotate_short_useful_tips_while_foundry_works_cover_reference_images_workflow")},
            {title: msg("common.more_translations"), description: msg("common.add_carefully_reviewed_interface_translations_while_keeping_model_names_cont")},
        ],
    },
    {
        id: "models", title: msg("common.model_management"), summary: msg("common.make_installed_models_easier_to_find_and_manage_in_settings"),
        items: [
            {title: msg("common.sort_installed_models_by_name_date_added_and_size"), status: "Available", description: msg("common.settings_remembers_your_sort_order_date_added_is_the_file_creation_date_on_t")},
            {title: msg("common.open_models_folder"), status: "Available", description: msg("common.open_comfyui_s_primary_models_folder_in_windows_explorer")},
        ],
    },
    {
        id: "workflow", title: msg("common.current_workflow_improvements"), summary: msg("common.build_on_the_image_creation_and_image_to_3d_workflows_already_in_use"),
        items: [
            {title: msg("common.better_vehicle_prop_and_creature_turnarounds"), status: "Evaluate", description: msg("common.revisit_the_original_turnaround_recipe_and_published_guidance_for_each_categ")},
            {title: msg("common.category_specific_view_sets"), status: "Evaluate", description: msg("common.determine_how_many_views_each_category_needs_and_which_angles_help_investiga")},
            {title: msg("common.better_ccore_memory_management"), status: "Planned", description: msg("common.evaluate_tighter_gpu_memory_estimates_and_memory_profile_defaults_for_longer")},
            {title: msg("common.ccore_prop_animation_controls"), status: "Evaluate", description: msg("common.qualify_ccore_s_author_supported_animation_on_representative_props_and_expos")},
            {title: msg("common.anima_support_for_image_creation"), status: "Planned", description: msg("common.add_anima_as_a_model_choice_in_create_images_with_guidance_for_its_supported")},
            {title: msg("common.enhance_prompt_in_image_creation"), description: msg("common.add_an_optional_language_model_prompt_enhancement_button_that_preserves_the")},
            {title: msg("common.refinement_comparisons"), status: "Evaluate", description: msg("common.keep_one_refinement_pass_recommended_compare_optional_rear_then_front_passes")},
        ],
    },
    {
        id: "upcoming", title: msg("common.upcoming_workflows"), summary: msg("common.complete_the_remaining_coming_soon_workflows_each_with_its_own_clear_ownersh"),
        items: [
            {title: msg("common.refine_and_repair_an_existing_mesh"), description: msg("common.start_with_an_existing_mesh_and_matching_reference_images_provide_a_dedicate")},
            {title: msg("common.start_with_a_video"), description: msg("common.investigate_selecting_useful_frames_and_reconstructing_an_asset_from_video_t")},
            {title: msg("common.pc_controlled_turntable_and_camera_capture"), description: msg("common.develop_capture_around_a_compatible_comxim_bluetooth_turntable_research_came")},
            {title: msg("common.action_figure_mode"), description: msg("common.use_identity_and_style_references_with_toy_or_figurine_presets_poses_and_opt")},
            {title: msg("common.print_service_handoff"), status: "Evaluate", description: msg("common.research_service_specific_file_requirements_physical_print_checks_upload_api")},
        ],
    },
    {
        id: "research", title: msg("common.models_tools_to_evaluate"), summary: msg("common.research_candidates_not_promised_integrations_verify_availability_licenses_a"),
        items: [
            {title: msg("common.hunyuan3d_2_1"), status: "Evaluate", description: msg("common.compare_its_initial_geometry_with_pixal3d_trellis_on_the_same_vehicle_prop_a"), source: "https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1", sourceLabel: "Official project"},
            {title: msg("common.skintokens_tokenrig"), status: "Evaluate", description: msg("common.evaluate_automatic_skeleton_and_skin_weight_generation_on_our_finished_meshe"), source: "https://github.com/VAST-AI-Research/SkinTokens", sourceLabel: "Official project"},
            {title: msg("common.kimodo"), status: "Evaluate", description: msg("common.evaluate_text_driven_character_motion_and_preset_animations_after_rigging_ch"), source: "https://github.com/nv-tlabs/kimodo", sourceLabel: "Official project"},
            {title: msg("common.ultratex"), status: "Evaluate", description: msg("common.investigate_texturing_existing_geometry_and_the_reported_2k_albedo_and_metal"), source: "https://www.reddit.com/r/TopologyAI/comments/1wzlljg/new_opensource_ai_texturing_for_3d_models_at_2k/", sourceLabel: "Research lead"},
            {title: msg("common.unimate"), status: "Evaluate", description: msg("common.identify_the_exact_project_and_evaluate_its_rigging_or_animation_capabilitie")},
            {title: msg("common.sam_3d_body"), status: "Evaluate", description: msg("common.evaluate_human_reconstruction_clothed_and_stylized_subjects_and_compatibilit")},
            {title: msg("common.kimi_procedural_3d_scripting"), status: "Evaluate", description: msg("common.verify_the_supplied_model_and_release_claims_then_investigate_editable_code"), source: "https://x.com/Kimi_Moonshot/status/2113680701770068067", sourceLabel: "Unverified research lead"},
            {title: msg("common.strand_based_groom_export"), status: "Evaluate", description: msg("common.research_creating_and_exporting_suitable_curves_as_alembic_for_unreal_s_groo")},
        ],
    },
    {
        id: "integration", title: msg("common.architecture_integration"), summary: msg("common.shared_requirements_for_future_workflow_additions_and_releases"),
        items: [
            {title: msg("common.independent_workflows_shared_services"), description: msg("common.give_each_workflow_a_dedicated_graph_section_and_cohesive_code_ownership_reu")},
            {title: msg("common.memory_profiles_that_affect_the_workflow"), description: msg("common.keep_the_working_default_profile_including_the_tested_splat_solid_path_quali")},
            {title: msg("common.mcp_and_export_documentation_parity"), description: msg("common.expose_new_workflow_choices_to_agents_and_keep_package_readme_contents_file")},
            {title: msg("common.foundry_mcp_workflow_access"), status: "Available", description: msg("common.discover_workflow_controls_run_stages_inspect_comfyui_graphs_and_retrieve_as")},
            {title: msg("common.foundry_skill_for_claude_and_codex"), status: "Available", description: msg("common.use_the_bundled_companion_skill_to_choose_a_workflow_let_foundry_work_locall")},
            {title: msg("common.connect_your_agent"), status: "Available", description: msg("agent_setup.how_to")},
            {title: msg("common.tripo_and_meshy_integrations"), status: "Planned", description: msg("common.evaluate_optional_asset_creation_and_handoffs_with_tripo_and_meshy")},
            {title: msg("common.expanded_hi3d_integration"), status: "Planned", description: msg("common.explore_more_ways_to_use_hi3d_alongside_the_existing_refinement_stages")},
            {title: msg("common.portable_updates_and_first_use_preparation"), description: msg("common.trace_dependencies_for_every_runtime_when_adding_features_check_access_and_p")},
        ],
    },
];
