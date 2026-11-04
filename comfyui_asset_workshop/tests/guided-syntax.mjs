import test from 'node:test';
import {readFileSync} from 'node:fs';
import {SourceTextModule} from 'node:vm';

test('independent method UI modules parse as browser modules',()=>{
    for(const name of ['guided/controller','guided/pages','guided/editor','guided/graph','views/home','shell','images/controller','../image-editor']){
        const file=new URL('../web/foundry/'+name+'.js',import.meta.url);
        new SourceTextModule(readFileSync(file,'utf8'),{identifier:file.href});
    }
});
