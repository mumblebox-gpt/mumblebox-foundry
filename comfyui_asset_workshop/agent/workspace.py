"""Discoverable MCP actions backed by the same service routes as Foundry's GUI."""
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

import base64

from mcp.types import ImageContent

from client import identifier


@dataclass(frozen=True)
class Action:
    method: str
    route: str
    help: str
    fields: str = ""
    params: tuple[str, ...] = ()
    query: tuple[str, ...] = ()
    link: bool = False


def read(route, help, params=(), query=()):
    return Action("GET", route, help, params=params, query=query)


def write(route, help, fields="", params=(), method="POST"):
    return Action(method, route, help, fields, params)


def file(route, help, params, query=()):
    return Action("GET", route, help, params=params, query=query, link=True)


RUN = ("run_id",)
IMAGE = ("creation_id",)
LIBRARY = ("asset_id",)
GROUPS = {
    "mesh": {
        "capabilities": read("/wizard/capabilities", "Single Image and Turnaround defaults, supported models, export formats and all quad solver controls."),
        "create": write("/wizard/runs", "Save a draft without generating.", "method, name, references, category, profile, overrides, selection, turnaround_model, image_creation"),
        "update": write("/wizard/runs/{run_id}", "Replace the idle run configuration.", "Full configuration from create", RUN, "PATCH"),
        "status": read("/wizard/runs/{run_id}", "Progress, checkpoints, settings, previews and export metadata.", RUN),
        "start": write("/wizard/runs/{run_id}/start", "Queue an owned stage. Single Image uses mesh, finish or rocket. Turnaround also offers turnaround.", "operation, request_id", RUN),
        "cancel": write("/wizard/runs/{run_id}/cancel", "Stop this run and keep its checkpoints.", params=RUN),
        "show": write("/wizard/runs/{run_id}/show", "Display this run in the open Foundry window.", params=RUN),
        "graph": read("/wizard/runs/{run_id}/graph", "Compiled native graph for the run's current stage or a recorded stage selected by name.", RUN, ("stage",)),
        "turnaround_graph": read("/wizard/runs/{run_id}/turnaround-graph", "Compiled Turnaround graph.", RUN),
        "single_template": read("/wizard/single-template", "Read the Single Image canvas recipe."),
        "package": file("/wizard/runs/{run_id}/package", "Download the completed asset ZIP.", RUN),
        "open_folder": write("/wizard/runs/{run_id}/open-folder", "Reveal the finished package folder in the desktop.", params=RUN),
    },
    "guided": {
        "capabilities": read("/guided/capabilities", "3D-Guided controls, geometry and texture settings, export defaults and resources."),
        "template": read("/guided/template", "Read the editable 3D-Guided graph template."),
        "create": write("/guided/runs", "Save a 3D-Guided draft. Show it to bind the selected Foundry graph before generation.", "name, original (imported filename), controls, image_creation"),
        "update": write("/guided/runs/{run_id}", "Revise the controls. Only affected downstream checkpoints are invalidated.", "controls object itself, including selected_view_ids and reference_view_id", RUN, "PATCH"),
        "status": read("/guided/runs/{run_id}", "Read stages, saved views, previews, exports and current controls.", RUN),
        "show": write("/guided/runs/{run_id}/show", "Bind this run to the selected Foundry wizard and wait for its acknowledgement.", params=RUN),
        "action": write("/guided/runs/{run_id}/action", "Run start, continue, resume, finish, rocket or cancel. Attach the GUI first for processing.", "operation, selection, overrides, request_id", RUN),
        "concept_edit": write("/guided/runs/{run_id}/concept-edit", "Start a masked edit of the concept sheet. Use the uploaded mask filename.", "mask_filename, prompt, feather, seed, replace_detail", RUN),
        "accept_concept_edit": write("/guided/runs/{run_id}/accept-concept-edit", "Accept a reviewed concept edit.", params=RUN),
        "graph": read("/guided/runs/{run_id}/graph", "Read the editable native graph for these controls.", RUN),
        "artifact": file("/guided/runs/{run_id}/artifacts/{key}", "Retrieve a saved view or mesh by its artifact key.", ("run_id", "key")),
        "package": file("/guided/runs/{run_id}/package", "Download the selected public asset ZIP.", RUN),
        "production": file("/guided/runs/{run_id}/production", "Build/download the private production archive. Review before sharing.", RUN),
        "open_folder": write("/guided/runs/{run_id}/open-folder", "Reveal the production folder in the desktop.", params=RUN),
        "open_package_folder": write("/guided/runs/{run_id}/open-package-folder", "Reveal the finished package folder in the desktop.", params=RUN),
    },
    "virtual_turntable": {
        "capabilities": read("/virtual-turntable/capabilities", "Virtual Turntable engines, controls, defaults, licenses and export choices."),
        "template": read("/virtual-turntable/template", "Read the editable Virtual Turntable graph."),
        "create": write("/virtual-turntable/runs", "Save one image and an explicitly selected reconstruction engine.",
                        "name, image (imported filename), engine, controls, selection, overrides, image_creation"),
        "update": write("/virtual-turntable/runs/{run_id}", "Update idle settings and invalidate affected stages.", "Full configuration from create", RUN, "PATCH"),
        "status": read("/virtual-turntable/runs/{run_id}", "Read completed stages, actual orbit, geometry previews and exported files.", RUN),
        "start": write("/virtual-turntable/runs/{run_id}/start", "Run turnaround, orbit, reconstruct, finish or rocket.", "operation, request_id", RUN),
        "cancel": write("/virtual-turntable/runs/{run_id}/cancel", "Cancel this run and retain completed stages.", params=RUN),
        "show": write("/virtual-turntable/runs/{run_id}/show", "Show this run in the live Foundry wizard.", params=RUN),
        "graph": read("/virtual-turntable/runs/{run_id}/graph", "Inspect the native graph for the chosen run and optional stage.", RUN, ("stage",)),
        "artifact": file("/virtual-turntable/runs/{run_id}/artifacts/{key}", "Retrieve the orbit, masked frames, raw mesh or finished mesh.", ("run_id", "key")),
        "package": file("/virtual-turntable/runs/{run_id}/package", "Download the selected outputs and their licensing record.", RUN),
    },
    "orbit_to_mesh": {
        "capabilities": read("/orbit-to-mesh/capabilities", "Orbit to Mesh presets, advanced controls, setup, licenses and exports."),
        "template": read("/orbit-to-mesh/template", "Read the independent Orbit to Mesh ComfyUI graph."),
        "create": write("/orbit-to-mesh/runs", "Save one reference image and a Pixal3D orbit recipe.",
                        "name, image (imported filename), controls, selection, overrides, exclude_views, image_creation"),
        "update": write("/orbit-to-mesh/runs/{run_id}", "Update idle settings or exclude source-frame IDs. Keep the front and one other view.", "Full configuration from create", RUN, "PATCH"),
        "status": read("/orbit-to-mesh/runs/{run_id}", "Read the orbit, proposed masked views with calibrated camera poses, mesh previews and outputs.", RUN),
        "start": write("/orbit-to-mesh/runs/{run_id}/start", "Run turnaround, orbit, cameras (align and propose views), views (refresh from saved cameras), reconstruct, finish or rocket.", "operation, request_id", RUN),
        "cancel": write("/orbit-to-mesh/runs/{run_id}/cancel", "Stop this run and retain verified stage files.", params=RUN),
        "show": write("/orbit-to-mesh/runs/{run_id}/show", "Show this run in the live Foundry wizard.", params=RUN),
        "graph": read("/orbit-to-mesh/runs/{run_id}/graph", "Inspect the full native graph or the prompt for a selected stage.", RUN, ("stage",)),
        "artifact": file("/orbit-to-mesh/runs/{run_id}/artifacts/{key}", "Retrieve the orbit, view contact sheet or a mesh preview.", ("run_id", "key")),
        "package": file("/orbit-to-mesh/runs/{run_id}/package", "Download the selected outputs, exact view metadata and resource terms.", RUN),
    },
    "splat": {
        "capabilities": read("/splat/capabilities", "Read Splat & Solid configuration and output choices."),
        "template": read("/splat/template", "Read the native splat template."),
        "create": write("/splat/runs", "Save a splat draft without generating.", "Configuration returned by capabilities, with one imported image"),
        "update": write("/splat/runs/{run_id}", "Update idle splat controls.", "Full configuration from create", RUN, "PATCH"),
        "status": read("/splat/runs/{run_id}", "Read progress, files and geometry checks.", RUN),
        "start": write("/splat/runs/{run_id}/start", "Queue generation, cleanup, export or rocket. Show the run to review it.", "operation, request_id", RUN),
        "cancel": write("/splat/runs/{run_id}/cancel", "Stop this run and keep completed artifacts.", params=RUN),
        "show": write("/splat/runs/{run_id}/show", "Show the splat wizard in Foundry.", params=RUN),
        "graph": read("/splat/runs/{run_id}/graph", "Read the native graph for the selected stage.", RUN, ("stage", "full")),
        "file": file("/splat/runs/{run_id}/file", "Retrieve a saved preview, asset or package.", RUN, ("path", "download")),
    },
    "hair": {
        "capabilities": read("/hair/capabilities", "HairDeck models, defaults, official examples, previews, rig, material and export controls."),
        "example_image": file("/hair/examples/{example_id}/file", "Preview an official bundled HairDeck example.", ("example_id",)),
        "use_example": write("/hair/examples/{example_id}/use", "Select an official bundled HairDeck reference. Returns a Foundry input filename.", params=("example_id",)),
        "create": write("/hair/runs", "Save hair settings without generation.", "Configuration returned by capabilities, with one imported image"),
        "update": write("/hair/runs/{run_id}", "Update idle settings. Export-only changes retain matching cards and chains.", "Full configuration from create", RUN, "PATCH"),
        "status": read("/hair/runs/{run_id}", "Read variations, preview artifacts, exports and state.", RUN),
        "start": write("/hair/runs/{run_id}/start", "Queue generate, rig, preview, avatar_preview, motion_preview or export.", "operation, request_id, selected (variation index)", RUN),
        "cancel": write("/hair/runs/{run_id}/cancel", "Stop this job while preserving completed generations.", params=RUN),
        "show": write("/hair/runs/{run_id}/show", "Show the HairDeck wizard in Foundry.", params=RUN),
        "graph": read("/hair/runs/{run_id}/graph", "Read the native graph for the selected stage.", RUN, ("operation", "selected")),
        "file": file("/hair/runs/{run_id}/file", "Retrieve a recorded HairDeck file.", RUN, ("path", "download")),
    },
    "ccore": {
        "capabilities": read("/ccore/capabilities", "Text and Image + Text modes, the twelve wizard examples, model precisions and token limits."),
        "start": write("/ccore/runs", "Queue a prop generation. For Image + Text import an image with target ccore.", "request_id (32 lowercase hex), name, prompt, mode, image, seed, max_tokens, model_variant"),
        "status": read("/ccore/runs/{run_id}", "Read progress, retry choices, and model/package state.", RUN),
        "cancel": write("/ccore/runs/{run_id}/cancel", "Stop the selected prop job.", params=RUN),
        "show": write("/ccore/runs/{run_id}/show", "Show the selected prop in Foundry.", params=RUN),
        "enhance": write("/ccore/enhance", "Return a locally enhanced description for review.", "request_id (32 lowercase hex), prompt"),
        "translate": write("/ccore/translate", "Translate the description literally into English with the local helper. Review before generation; does not add design details. Choose q4 (less VRAM) or q8 (higher precision); GPU only.", "request_id (32 lowercase hex), prompt, precision (q4 or q8)"),
        "cancel_enhancement": write("/ccore/enhance/{run_id}/cancel", "Stop the matching description enhancement or translation.", params=RUN),
        "graph": read("/ccore/runs/{run_id}/graph", "Read the native prop generation graph.", RUN),
        "file": file("/ccore/runs/{run_id}/file", "Retrieve the prop GLB or ZIP.", RUN, ("kind", "download")),
    },
    "garment": {
        "capabilities": read("/garment/capabilities", "Garment modes, generation presets, settings and availability."),
        "start": write("/garment/runs", "Queue a Garment Particles generation with one or two imported references or a prompt.", "request_id (32 lowercase hex), name, mode, prompt, image, back_image, seed, points, steps"),
        "status": read("/garment/runs/{run_id}", "Read pattern, mesh, drape, rig and package state.", RUN),
        "show": write("/garment/runs/{run_id}/show", "Show this garment in Foundry.", params=RUN),
        "guide": read("/garment/runs/{run_id}/guide", "Read pattern and point selection information.", RUN),
        "mix_sources": read("/garment/runs/{run_id}/mix-sources", "List saved garment parts eligible for mixing.", RUN),
        "edit": write("/garment/runs/{run_id}/edit", "Queue an author-supported pattern edit using the saved guide.", "request_id, edit (fields by operation in capabilities), prompt, seed, points, steps", RUN),
        "sew": write("/garment/runs/{run_id}/sew", "Build a sewn mesh.", "budget", RUN),
        "drape": write("/garment/runs/{run_id}/drape", "Simulate cloth using the uploaded rigged character.", "character and drape controls from capabilities", RUN),
        "fit": write("/garment/runs/{run_id}/fit", "Transfer skin weights after reviewing the current drape.", "approve (current drape_id)", RUN),
        "package": write("/garment/runs/{run_id}/package", "Save the garment package.", params=RUN),
        "cancel": write("/garment/runs/{run_id}/cancel", "Stop only the matching job.", params=RUN),
        "graph": read("/garment/runs/{run_id}/graph", "Read the native generation and finishing node graph last queued.", RUN),
        "file": file("/garment/runs/{run_id}/file/{name}", "Retrieve a saved pattern, mesh or package by name.", ("run_id", "name"), ("download",)),
    },
    "images": {
        "capabilities": read("/images/capabilities", "Read image models, categories, reference slots, editing settings and defaults."),
        "loras": read("/asset-workshop/v2/loras", "List the same installed LoRAs and metadata used by Image Creator."),
        "checkpoints": read("/asset-workshop/v2/civitai/installed", "Read the installed image checkpoints available to Image Creator."),
        "gallery": read("/images", "Search and page through accepted images and pairs.", query=("search", "category", "kind", "sort", "cursor", "limit")),
        "create": write("/images", "Save a draft.", "name, category, model, description, front, back, references, settings, checkpoint, loras, graph_scope (optional ccore-reference)"),
        "update": write("/images/{creation_id}", "Update idle image settings.", "Full configuration from create", IMAGE, "PATCH"),
        "status": read("/images/{creation_id}", "Read progress, previews, edits and revisions.", IMAGE),
        "start": write("/images/{creation_id}/start", "Queue generate, regenerate or an edit prepared with foundry_image_prepare_edit.", "operation, request_id", IMAGE),
        "cancel": write("/images/{creation_id}/cancel", "Stop this creation while preserving its revisions.", params=IMAGE),
        "show": write("/images/{creation_id}/show", "Show the current image creation in Foundry.", params=IMAGE),
        "accept": write("/images/{creation_id}/accept", "Accept a reviewed candidate or restore a revision.", "revision_id, expected (current revision)", IMAGE),
        "save": write("/images/{creation_id}/save", "Save the accepted images to Gallery.", params=IMAGE),
        "handoff": write("/images/{creation_id}/handoff", "Copy accepted images to the 3D inputs with provenance.", "mode (single or pair), side (optional accepted single, front or back for single mode), revision_id (optional expected accepted revision)", IMAGE),
        "reuse": write("/images/{creation_id}/reuse", "Make a new draft from the saved image settings.", params=IMAGE),
        "removal_preview": write("/images/removal-preview", "Review exact Gallery entries/files before removal.", "ids, delete_files"),
        "remove": write("/images/remove", "Apply a preview token only after the user authorizes the listed removal.", "token"),
        "graph": read("/images/{creation_id}/graph", "Read the latest compiled image creation or edit graph.", IMAGE),
        "file": file("/images/{creation_id}/files/{revision}", "Retrieve a specific image revision.", ("creation_id", "revision"), ("download",)),
        "package": file("/images/{creation_id}/package", "Retrieve the accepted image package.", IMAGE),
    },
    "workspace": {
        "bootstrap": read("/bootstrap", "Read Foundry version, preferences, credits and saved package import candidates."),
        "graph": file("/workflow", "Read the full shipped Foundry ComfyUI graph. This graph contains the branches behind the wizards.", ()),
        "preferences": write("/preferences", "Update the shared Foundry settings.", "theme, language, profile, font_size, busy_motion, model_sort, auto_check_updates", method="PATCH"),
        "show": write("/workspace/show", "Open a section in the selected Foundry window without changing desktop focus.", "section (workflow, images, gallery, history, integrations, about, roadmap, settings)"),
        "status": read("/asset-workshop/status", "Read shared resource, workflow and model residency status."),
        "unload_models": write("/asset-workshop/release", "Ask the shared lifecycle owner to unload idle models."),
        "agent_connection": read("/agent/connection", "Read the bundled skill path and revision, app version, and connection-time update check."),
        "update_status": read("/updates/status", "Read the last version check."),
        "check_updates": write("/updates/check", "Check for a published preview.", "manual"),
        "models": read("/resources", "List installed model files.", query=("cursor", "limit", "sort")),
        "open_models": write("/resources/open-folder", "Reveal the primary local models folder."),
        "model_delete_preview": write("/resources/delete-preview", "Review the exact model file selected for deletion.", "id"),
        "model_delete": write("/resources/delete", "Delete the exact reviewed model file with user authorization.", "token"),
        "cache_preview": write("/cache/preview", "Review temporary files and incomplete downloads eligible for cleanup."),
        "cache_purge": write("/cache/purge", "Clear the chosen groups from the authorized preview.", "token, groups"),
        "library": read("/library", "List saved Foundry assets and packages.", query=("kind", "cursor", "limit")),
        "library_sync": write("/library/sync", "Refresh History from retained saved runs."),
        "library_import": write("/library/import-package", "Register an existing Foundry package shown in bootstrap.", "candidate_id"),
        "library_detail": read("/library/{asset_id}", "Read one History entry and its artifact list.", LIBRARY),
        "library_file": file("/library/{asset_id}/files/{file_id}", "Retrieve one saved History artifact.", ("asset_id", "file_id")),
        "library_open_folder": write("/library/{asset_id}/open-folder", "Reveal a saved asset's desktop folder.", params=LIBRARY),
        "library_removal_preview": write("/library/removal-preview", "Review the exact History entries/files selected for removal.", "kind, ids, delete_files"),
        "library_remove": write("/library/remove", "Apply the exact user-authorized History removal.", "token"),
        "hugging_face": write("/asset-workshop/hugging-face", "Connect or disconnect a Hugging Face credential when explicitly requested.", "action, token when connecting"),
        "civitai_status": read("/asset-workshop/v2/civitai/status", "Read Civitai connection and download status."),
        "civitai_credentials": write("/asset-workshop/v2/civitai/connection", "Connect or disconnect a Civitai credential when explicitly requested.", "action, token when connecting, client_id when configuring"),
        "civitai_resolve": write("/asset-workshop/v2/civitai/resolve-url", "Resolve a Civitai model URL using the existing integration.", "url, profile, nsfw"),
        "civitai_search": read("/asset-workshop/v2/civitai/search", "Search Civitai through Foundry's integration.", query=("query", "profile", "kind", "nsfw", "cursor", "sort", "period")),
        "civitai_model": read("/asset-workshop/v2/civitai/model/{model_id}", "Read compatible file choices for a Civitai model.", ("model_id",), ("profile", "nsfw")),
        "civitai_installed": read("/asset-workshop/v2/civitai/installed", "Read Civitai files installed by Foundry."),
        "civitai_download": write("/asset-workshop/v2/civitai/download", "Download the exact selected compatible Civitai file.", "model_id, version_id, file_id, profile, kind"),
        "civitai_download_control": write("/asset-workshop/v2/civitai/download/control", "Control the current integration download.", "action"),
    },
}


def describe(workflow=None):
    if workflow is None:
        return {"workflows": list(GROUPS)}
    if workflow not in GROUPS:
        raise ValueError("Choose a workflow from foundry_workflows.")
    related = ["foundry_import_reference"] if workflow != "workspace" else []
    if workflow == "images":
        related.append("foundry_image_prepare_edit")
    if workflow == "garment":
        related.append("foundry_garment_upload_character")
    related.append("foundry_read_image_preview")
    return {"workflow": workflow, "related_tools": related, "actions": {
        name: {"description": action.help, "path_parameters": list(action.params),
               "query_parameters": list(action.query), "body_fields": action.fields,
               "method": action.method, "returns_link": action.link}
        for name, action in GROUPS[workflow].items()
    }}


def segment(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 160 or ".." in value
            or any(ch in value for ch in "/\\%?#") or any(ord(ch) < 32 for ch in value)):
        raise ValueError("Use one recorded artifact identifier.")
    return quote(value, safe="")


def call(client, workflow, action, params=None, body=None, query=None):
    route = GROUPS.get(workflow, {}).get(action)
    if route is None:
        raise ValueError("Choose an action from foundry_workflows.")
    params, query = params or {}, query or {}
    if set(params) != set(route.params) or set(query) - set(route.query):
        raise ValueError("Use the recorded path parameters and documented query parameters for this action.")
    if any(type(value) not in (str, int, bool) for value in query.values()):
        raise ValueError("Use simple text, number or boolean query values.")
    path = route.route.format(**{
        key: segment(value) if key in ("key", "name", "file_id") else identifier(value)
        for key, value in params.items()
    })
    if query:
        path += "?" + urlencode({key: str(value).lower() if isinstance(value, bool) else value
                                 for key, value in query.items()})
    api = client.upload_api if path.startswith("/asset-workshop/") else client
    if route.method == "GET":
        if body is not None:
            raise ValueError("Read actions use params or query only.")
        if route.link:
            return {"url": api.base_url + path, "description": route.help}
        return api.request(path)
    data = dict(body or {})
    if workflow != "workspace":
        data.pop("client_id", None)
        data.pop("workflow_path", None)
    if action == "start" or (workflow == "garment" and action in ("edit", "sew", "drape", "fit")):
        data["client_id"] = "foundry-agent"
    return api.request(path, data, method=route.method)


def image_preview(client, url):
    parts = urlsplit(url)
    origin = urlsplit(client.origin)
    if parts.netloc and (parts.scheme, parts.netloc) != (origin.scheme, origin.netloc):
        raise ValueError("Read only a recorded image from this Foundry installation.")
    if parts.fragment or (parts.scheme and not parts.netloc):
        raise ValueError("Use a recorded local image URL.")
    path = parts.path
    foundry_path = path.startswith("/mumblebox-foundry/v1/") and (
        "/files/" in path or "/file/" in path or path.endswith("/file") or "/artifacts/" in path
    )
    if path != "/view" and not foundry_path:
        raise ValueError("Use an image URL returned by a Foundry preview, run or library entry.")
    data = client.upload_api.request(path + ("?" + parts.query if parts.query else ""), binary=True)
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ValueError("This artifact is not a supported image. Follow its download URL instead.")
    return ImageContent(type="image", mimeType=mime, data=base64.b64encode(data).decode("ascii"))


def register(server, client, checked):
    def tool(function):
        return server.tool(structured_output=True)(checked(function))

    @tool
    def foundry_workflows(workflow: str | None = None) -> dict[str, Any]:
        """List Foundry workflow groups, or describe all actions and parameters for one group."""
        return describe(workflow)

    @tool
    def foundry_workflow_action(workflow: str, action: str, params: dict[str, str] | None = None,
                               body: dict[str, Any] | None = None,
                               query: dict[str, str | int | bool] | None = None) -> dict[str, Any]:
        """Call a documented workflow action. Read foundry_workflows and the group's capabilities first."""
        return call(client, workflow, action, params, body, query)

    @server.tool(structured_output=False)
    @checked
    def foundry_read_image_preview(url: str):
        """Read a small Foundry PNG, JPEG or WebP as actual image content for review."""
        return image_preview(client, url)

    @tool
    def foundry_garment_upload_character(run_id: str, path: str) -> dict[str, Any]:
        """Upload an authorized rigged GLB to a sewn garment run. Returns the character ID for drape."""
        source = client.allowed_input(path)
        if source.suffix.lower() != ".glb" or source.stat().st_size > 150 * 1024**2:
            raise ValueError("Choose a rigged GLB smaller than 150 MB.")
        with source.open("rb") as stream:
            return client.request(f"/garment/runs/{identifier(run_id)}/character", stream,
                                  method="POST", content_type="application/octet-stream",
                                  content_length=source.stat().st_size)

