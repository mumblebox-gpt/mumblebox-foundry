module.exports = {
  daemon:true,
  run:[
    {method:"shell.run",params:{venv:".pinokio/launcher-env",message:"python scripts/pinokio/runtime.py --root .",on:[{event:"/Foundry could not start:/",break:true},{event:"/Foundry ready: (http:\\/\\/[0-9.:]+) (http:\\/\\/localhost:[0-9]+\\/mumblebox-foundry\\/\\?version=[A-Za-z0-9.-]+) \\[ready\\]/",done:true}]}},
    {method:"local.set",params:{url:"{{input.event[1]}}",workspace:"{{input.event[2]}}"}}
  ]
};
