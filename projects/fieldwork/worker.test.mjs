import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from './src/worker.mjs';
test('publication retries, room filters and private notebooks',async()=>{
 const data=new Map(),env={BUCKET:{put:(k,v)=>data.set(k,v),get:k=>data.has(k)?{json:()=>JSON.parse(data.get(k))}:null,list:({prefix})=>({objects:[...data.keys()].filter(k=>k.startsWith(prefix)).map(key=>({key}))})}};
 const call=(path,payload,user)=>worker.fetch(new Request('https://example.test/api/'+path,{method:payload?'POST':'GET',headers:{'Content-Type':'application/json',...(user?{'oai-authenticated-user-id':user}:{})},body:payload?JSON.stringify(payload):undefined}),env);
 const post={room:'course',date:'2026-01-01',title:'Demo',body:'Test the retry.'};
 await call('publish',post);await call('publish',post);
 assert.equal((await (await call('feed?room=course')).json()).posts.length,1);
 assert.equal((await (await call('feed?room=news')).json()).posts.length,0);
 assert.equal((await (await call('post?id=course/2026-01-01')).json()).body,post.body);
 assert.equal((await call('publish',{...post,room:'invalid'})).status,400);
 const path='notebook?id=course/2026-01-01',note={note:'My proof',saved:true};
 assert.equal((await call(path,note)).status,401);await call(path,note,'one');
 assert.deepEqual(await (await call(path,undefined,'one')).json(),note);
 assert.equal((await (await call(path,undefined,'two')).json()).note,'');
});
