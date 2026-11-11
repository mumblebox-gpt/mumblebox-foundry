"""Render a localized root README from the unchanged machine-readable package catalog."""
import html
import re
from urllib.parse import quote

try:  # Also supports the portable finishing tools imported as a top-level package.
    from ..foundry.localization import translate, translate_source
except ImportError:
    from foundry.localization import translate, translate_source


def text(value):
    return html.escape(str(value), quote=False).replace("|", r"\|").replace("\r", " ").replace("\n", " ").replace(chr(96), "\\" + chr(96)).replace("[", r"\[").replace("]", r"\]")


def anchor(path):
    return "dir-" + re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")


def link(path, label=None):
    return "[" + text(label or path) + "](" + quote(path, safe="/._-") + ")"


LABELS = {key: key for key in ("vertices", "triangles", "quads", "ngons", "polygons", "uv_layers", "objects", "dimensions", "units", "up_axis", "boundary_edges", "nonmanifold_edges", "degenerate_triangles", "components", "watertight", "winding_consistent")}


class ReadmeWriter:
    """Presentation only: paths, user names, prompts, licenses and catalog fields stay intact."""
    def __init__(self, locale):
        self.locale = locale

    def say(self, key, **values):
        return translate("package." + key, values, self.locale)

    def human(self, value):
        return text(translate_source(value, self.locale))

    def fmt(self, value):
        if value is None:
            return self.say("not_recorded")
        if isinstance(value, bool):
            return self.say("yes" if value else "no")
        if isinstance(value, int):
            return f"{value:,}"
        if isinstance(value, float):
            return f"{value:.6g}"
        if isinstance(value, (list, tuple)):
            return " × ".join(self.fmt(item) for item in value)
        return text(value)

    def table(self, *headers):
        return ["| " + " | ".join(self.say(key) for key in headers) + " |", "|" + "---|" * len(headers)]

    def file_table(self, files, prefix=""):
        return self.table("filename", "contents") + ["| " + link(f.path, f.path.removeprefix(prefix)) + " | " + self.human(f.description) + " |" for f in sorted(files, key=lambda f: (f.kind == "texture", f.path.casefold()))]

    def measurement_lines(self, measurements):
        groups = [("geometry", measurements.get("geometry") or {k: v for k, v in measurements.items() if k in LABELS})]
        groups += [(title, measurements.get(key, {})) for title, key in (("authoring_geometry", "authoring"), ("runtime_geometry", "runtime"), ("coordinates", "coordinates"), ("topology", "topology"), ("grounding", "grounding"))]
        lines = []
        for title, data in groups:
            if data:
                lines += ["**" + self.say(title) + "**", ""] + self.table("measurement", "value")
                lines += ["| " + (self.say(k) if k in LABELS else self.human(k.replace("_", " ").title())) + " | " + self.fmt(v) + " |" for k, v in data.items() if not isinstance(v, dict)] + [""]
        maps = measurements.get("textures", [])
        if maps:
            lines += ["**" + self.say("texture_specs") + "**", ""] + self.table("file", "texture_dimensions", "interpretation")
            lines += ["| " + text(item["path"]) + " | " + self.fmt(item.get("dimensions")) + " | " + self.human(item.get("interpretation", self.say("not_recorded"))) + " |" for item in maps] + [""]
        return lines

    def render(self, c):
        say = self.say
        project = text(c.project_identity.get("name") or "Mumblebox")
        lines = ["# " + say("title", asset=text(c.asset_name), project=project), "", say("intro"), ""] + self.table("package_info", "value")
        for key, value in (("asset", text(c.asset_name)), ("export_date", text(c.created_utc)), ("export_id", text(c.export_id)), ("workflow_version", self.fmt(c.workflow_version)), ("schema", text(c.schema))):
            lines += ["| " + say(key) + " | " + value + " |"]
        lines += ["", say("relative_paths"), "", "## " + say("directory_index"), ""]
        dirs = [v.directory for v in c.variants]
        dirs += [directory for directory in ("Metadata/", "Licenses/") if any(f.path.startswith(directory) for f in c.files)]
        lines += ["- [" + text(d) + "](#" + anchor(d) + ")" for d in dirs] + ["", "## " + say("directory_contents"), ""]
        for v in c.variants:
            lines += ['<a id="' + anchor(v.directory) + '"></a>', "### " + text(v.directory), "", self.human(v.description)]
            if v.intended_use:
                lines += ["", self.human(v.intended_use)]
            lines += ["", "**" + say("files") + "**", ""] + self.file_table([f for f in c.files if f.variant_id == v.id], v.directory) + [""] + self.measurement_lines(v.measurements)
            lines += ["**" + say("validation") + "**", ""]
            if v.validations:
                for val in v.validations:
                    record = val if isinstance(val, dict) else vars(val)
                    lines += ["- " + self.human(record["name"]) + ": " + self.human(record["status"].replace("_", " ")) + (". " + self.human(record["note"]).rstrip(".") if record.get("note") else "") + "."]
            else:
                lines += ["- " + say("no_validation")]
            if v.limitations:
                lines += ["", "**" + say("limitations") + "**", ""] + ["- " + self.human(item) for item in v.limitations]
            lines += [""]
        for directory, desc in (("Metadata/", "metadata_description"), ("Licenses/", "licenses_description")):
            files = [f for f in c.files if f.path.startswith(directory)]
            if not files:
                continue
            lines += ['<a id="' + anchor(directory) + '"></a>', "### " + directory, "", say(desc), "", "**" + say("files") + "**", ""] + self.file_table(files, directory) + ["", "**" + say("specifications") + "**", ""]
            specs = [say(k) for k in ("json_format", "paths_spec", "hash_spec", "manifest_spec")] if directory == "Metadata/" else [say("license_count", count=len(files)), say("source_not_rewritten")]
            lines += ["- " + value for value in specs] + [""]
        lines += ["## " + say("production_record"), ""]
        if c.production.get("method") == "3d-guided/v1":
            lines += ["### " + say("guided_method"), "", say("guided_description"), "", "- " + say("selected_views", views=text(", ".join(c.production.get("selected_view_ids", [])))), "- " + say("finishing_reference", reference=text(c.production.get("reference_view_id", say("not_recorded"))))]
            lines += ["- " + say(key) for key in ("camera_records", "private_production")] + [""]
        creation = c.production.get("image_creation")
        if creation:
            lines += ["### " + say("reference_images"), "", say("reference_description"), ""] + self.table("view", "image_model", "seed", "recorded_license")
            for image in creation.get("images", []):
                provenance = image["provenance"]
                lines += ["| " + text(image["side"]) + " | " + text(provenance.get("profile", say("not_recorded"))) + " | " + self.fmt(provenance.get("seed")) + " | " + text(provenance.get("model_license", {}).get("label", say("not_recorded"))) + " |"]
            for image in creation.get("images", []):
                provenance = image["provenance"]
                terms = provenance.get("model_license", {})
                if terms.get("url"):
                    lines += ["", say("model_terms", side=text(image["side"].title()), url=text(terms["url"])), ""]
                checkpoint = provenance.get("checkpoint", {})
                if checkpoint:
                    lines += ["- " + say("checkpoint", model=text(checkpoint.get("model_name", "External checkpoint")), url=text(checkpoint.get("source_url", say("not_recorded"))))]
                for lora in provenance.get("loras", []):
                    lines += ["- " + say("lora", name=text(lora.get("name", say("not_recorded"))), url=text(lora.get("civitai", {}).get("source_url", say("consult_provider"))))]
            lines += ["", say("image_terms_note"), ""]
        quad = c.production.get("quad_retopology") or {}
        if quad.get("requested_method"):
            names = {"quadriflow": "QuadriFlow CPU", "instant_meshes": "Instant Meshes CPU", "cyber_cuda": "CyberRemesher NVIDIA CUDA", "topology_preserving": "Foundry topology-preserving subdivision"}
            used = ", ".join(names.get(method, method) for method in quad.get("effective_methods", []))
            lines += ["### " + say("quad_retopology"), "", "- " + say("requested_method", method=text(names.get(quad["requested_method"], quad["requested_method"]))), "- " + say("effective_methods", methods=text(used or say("no_remeshing"))), ""]
        turnaround = c.production.get("turnaround", {})
        if turnaround:
            lines += ["### " + say("turnaround_settings"), ""] + self.table("setting", "recorded_value")
            if c.production.get("category"):
                lines += ["| " + say("asset_category") + " | " + text(c.production["category"]) + " |"]
            for key, label in (("name", "image_model"), ("recipe", "prompt_recipe"), ("guidance", "instruction_source"), ("width", "sheet_width"), ("height", "sheet_height"), ("steps", "sampling_steps"), ("cfg", "guidance_scale"), ("seed", "seed"), ("sampler", "sampler"), ("scheduler", "scheduler")):
                if key in turnaround:
                    lines += ["| " + say(label) + " | " + self.fmt(turnaround[key]) + " |"]
            lines += [""]
        if c.resources:
            lines += self.table("stage", "resource", "version", "source")
            for resource in c.resources:
                url = resource.get("source")
                source = "[" + say("project") + "](" + quote(url, safe=":/._-#") + ")" if url else say("not_recorded")
                lines += ["| " + self.human(resource.get("stage", say("not_recorded"))) + " | " + text(resource["name"]) + " | " + self.fmt(resource.get("version")) + " | " + source + " |"]
            lines += ["", "### " + say("resource_licenses"), ""]
            for resource in c.resources:
                url = resource.get("license_url")
                source = " [" + say("license") + "](" + quote(url, safe=":/._-#") + ")" if url else ""
                lines += ["- **" + text(resource["name"]) + "** — " + text(resource.get("license") or say("not_recorded")) + ". " + self.human(resource.get("license_summary") or say("consult_notices")) + source]
        else:
            lines += [say("no_provenance")]
        if c.warnings:
            lines += ["", "**" + say("documentation_status") + "**", ""] + ["- " + self.human(item) for item in c.warnings]
        lines += ["", "## " + say("about", project=project), "", self.human(c.project_identity.get("description") or "")]
        for key, label in (("github_url", "project_repository"), ("homepage_url", "homepage"), ("pinokio_url", None)):
            url = c.project_identity.get(key)
            if url:
                lines += ["", (say(label) if label else "Pinokio") + ": [" + text(url) + "](" + quote(url, safe=":/._-#") + ")"]
        terms = c.project_identity.get("terms")
        lines += ["", "## " + say("terms_heading"), "", say("terms_version", path=text(terms["path"]), version=text(terms.get("version", say("not_recorded")))) if terms else say("no_terms"), "", say("no_asset_license"), ""]
        return "\n".join(lines)


def render_readme(catalog, locale="en"):
    return ReadmeWriter(locale).render(catalog)
