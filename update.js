const path = require('path');
const start = path.resolve(__dirname, 'start.js');
module.exports = {
  requires:{bundle:"ai"},
  run:[
    {method:"shell.run",params:{venv:".pinokio/envs/host",message:"python scripts/pinokio/maintenance.py update --root .",on:[
      {event:"/Foundry maintenance stopped:/",break:true},
      {event:"/Foundry update result: (installed|current) \\[done\\]/",done:true}
    ]}},
    {method:"local.set",params:{updateResult:"{{input.event[1]}}"}},
    {method:"notify",when:"{{local.updateResult === 'current'}}",params:{html:"Foundry is already up to date.",silent:true}},
    {method:"script.restart",when:"{{local.updateResult === 'installed'}}",params:{uri:start}}
  ]
};
