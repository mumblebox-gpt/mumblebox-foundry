"""Bounded localhost adapter for the same Foundry runs used by the wizard."""
import uuid
from client import LocalAPI, identifier

class FoundryAPI(LocalAPI):
    def __init__(self,base_url="http://127.0.0.1:8188",**kwargs):
        super().__init__(base_url,**kwargs)
        self.origin=base_url.rstrip("/")
        self.base_url=self.origin+"/mumblebox-foundry/v1"
        self.upload_api=LocalAPI(base_url,**kwargs)
        self.upload_api.base_url=self.origin

    def capabilities(self):return self.request("/wizard/capabilities")

    def import_reference(self,path,role="primary",description="",target=""):
        if target not in ("", "ccore"):
            raise ValueError("Choose the default upload or target ccore.")
        if role not in ("primary","back","face","component","style","detail"):
            raise ValueError("Use primary, back, face, component, style or detail.")
        if len(description)>800:raise ValueError("Keep the reference description under 800 characters.")
        source=self.allowed_input(path)
        if source.stat().st_size>20*1024**2:raise ValueError("References must be smaller than 20 MB.")
        if source.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            raise ValueError("Choose a PNG, JPEG or WebP image.")
        subfolder = "foundry-references" if target == "ccore" else "foundry-agent"
        data,kind=self.multipart({"type":"input","subfolder":subfolder,"overwrite":"false"},"image",source)
        result=self.upload_api.request("/upload/image",data,content_type=kind)
        return {"id":uuid.uuid4().hex,"filename":"/".join(filter(None,[result.get("subfolder"),result["name"]])),
                "role":role,"description":description}

    def create_run(self,configuration):return self.request("/wizard/runs",configuration)
    def update_run(self,run_id,configuration):
        return self.request("/wizard/runs/"+identifier(run_id),configuration,method="PATCH")
    def get_run(self,run_id):
        result=self.request("/wizard/runs/"+identifier(run_id))
        # Mesh previews have URLs. Large graph output records are GUI internals.
        return {k:v for k,v in result.items() if k not in ("outputs","reference_prompt")}
    def start(self,run_id,operation,request_id):
        if operation not in ("turnaround","mesh","finish","rocket"):
            raise ValueError("Choose turnaround, mesh, finish or rocket.")
        return self.request("/wizard/runs/"+identifier(run_id)+"/start",
            {"operation":operation,"request_id":identifier(request_id),"client_id":"foundry-agent"})
    def cancel(self,run_id):return self.request("/wizard/runs/"+identifier(run_id)+"/cancel",{})
    def show(self,run_id):return self.request("/wizard/runs/"+identifier(run_id)+"/show",{})
    def package(self,run_id):
        run=self.get_run(run_id)
        if not run.get("package"):raise ValueError("This run has no completed package yet.")
        return {"run_id":run_id,"package":run["package"],"download_url":self.base_url+"/wizard/runs/"+identifier(run_id)+"/package"}
