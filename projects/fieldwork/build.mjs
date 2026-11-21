import {mkdir,readFile,writeFile,copyFile} from 'node:fs/promises';
const page=await readFile('src/index.html','utf8');
const worker=await readFile('src/worker.mjs','utf8');
await mkdir('dist/server',{recursive:true});await mkdir('dist/.openai',{recursive:true});
await writeFile('dist/server/index.js','const PAGE='+JSON.stringify(page)+';\n'+worker);
await copyFile('.openai/hosting.json','dist/.openai/hosting.json');
