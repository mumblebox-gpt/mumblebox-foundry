import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=(await readFile(new URL('../web/foundry/hair/review.js',import.meta.url),'utf8')).replace(/^import .*;\r?\n/gm,'').replaceAll('export ','');
const {displayFiles,preprocessingWarnings}=new Function(source+';return {displayFiles,preprocessingWarnings};')();
test('older saved HairDeck output manifests expose the actual processing, result and UV sheets',()=>{
 const files=['preprocess_00001_.png','preview_00001_.png','uv_layout.png','cards.json'].map(filename=>({filename,subfolder:'saved'}));
 assert.deepEqual(displayFiles({files}).map(f=>[f.group,f.path]),[['input','saved/preprocess_00001_.png'],['result','saved/preview_00001_.png'],['material','saved/uv_layout.png']]);
});
test('official uncertain-mask and low-confidence-crop messages are visible and not repeated',()=>{
 const result=preprocessingWarnings({preprocess_notes:{status:'ok',notes:['matte_uncertain','box_from_low_scores','matte_uncertain']}});
 assert.equal(result.length,2);assert.match(result[0],/segmentation/);assert.match(result[1],/low confidence/);
});
