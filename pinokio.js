module.exports = {
  version:"8.0.0",
  title:"Mumblebox 3D Asset Foundry",
  description:"Make images and 3D assets locally for games, 3D printing, and creative projects. Foundry gives you guided workflows, automatic setup, and export options for each use. Use it on its own or connect your coding agent with the included MCP server and companion skill. Give your agent a head start with locally generated assets, so it can spend less time and fewer tokens building from scratch. Interface in English, Simplified Chinese, Latin American Spanish, French, and Brazilian Portuguese. Windows/NVIDIA preview.",
  icon:"icon.png",
  menu:async(kernel,info)=>{
    for(const [script,label] of [["install.js","Installing software"],["repair.js","Repairing software"],["update.js","Updating Foundry"]]){
      if(info.running(script))return [{default:true,text:label,icon:"fa-solid fa-terminal",href:script}];
    }
    if(!info.exists('.pinokio/installed.json'))return [{default:true,text:"Install",icon:"fa-solid fa-download",href:"install.js"}];
    if(info.running('start.js')){
      const runtime=info.local('start.js');
      // Pinokio Desktop is served from localhost. Match that site so ComfyUI's
      // cross-site request protection permits its embedded workspace. Backend
      // and MCP endpoints remain bound to 127.0.0.1; do not weaken CORS checks.
      const workspace=runtime?.url?new URL('/mumblebox-foundry/',runtime.url):null;
      if(workspace?.hostname==='127.0.0.1')workspace.hostname='localhost';
      return [...(workspace?[{default:true,text:"Open Foundry",icon:"fa-solid fa-cubes",href:workspace.href}]:[]),
        {default:!runtime?.url,text:"Startup logs",icon:"fa-solid fa-terminal",href:"start.js"},
        {text:"Update",icon:"fa-solid fa-arrows-rotate",href:"update.js",
          confirm:"Update Foundry to the latest published version? Foundry will stop and restart. Saved assets, models and settings are preserved. Active generation must finish first."}];
    }
    return [{default:true,text:"Start Foundry",icon:"fa-solid fa-play",href:"start.js"},
      {text:"Update",icon:"fa-solid fa-arrows-rotate",href:"update.js"},
      {text:"Repair software",icon:"fa-solid fa-wrench",href:"repair.js"},
      {text:"Installation and MCP help",icon:"fa-solid fa-book",href:"https://github.com/mumblebox-gpt/mumblebox-foundry/blob/codex/initial-import/docs/PINOKIO.md"}];
  }
};
