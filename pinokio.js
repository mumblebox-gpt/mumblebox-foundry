module.exports = {
  version:"8.0.0",
  title:"Mumblebox 3D Asset Foundry",
  description:"Make 3D gaming assets on your GPU, from quick blockouts to finished textured models for Blender. Build props and character parts, generate rigged hair and Gaussian splats, or export meshes for 3D printing. Guided wizards take you from an image or prompt through preview, refinement, and export. Pinokio sets up Foundry, and Orbit with Splats prepares Brush automatically when you first train a splat. Use Foundry on its own or connect Codex, Claude Code, or another MCP-enabled coding agent. The included MCP and companion skill let your agent hand generation to your GPU and pick up the result in Blender, saving time and tokens on the first pass. Windows/NVIDIA preview. Available in English, Simplified Chinese, Latin American Spanish, French, Brazilian Portuguese, German, Japanese, Korean, and Hindi. Make your next asset here! 用中文做出你的下一个 3D 素材！ ¡Crea tu próximo asset en español! Créez votre prochain objet 3D en français ! Crie seu próximo asset em português! Erstelle dein nächstes 3D-Asset auf Deutsch! 日本語で次の3Dアセットを作ろう！ 한국어로 다음 3D 에셋을 만들어 보세요! अपना अगला 3D एसेट हिंदी में बनाएँ!",
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
