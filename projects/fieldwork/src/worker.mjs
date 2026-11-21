const rooms = ['course','socratic','skills','news','agents','desk'];
const json = (data,status=200) => Response.json(data,{status,headers:{'Cache-Control':'private, no-store'}});
const pattern = /^(course|socratic|skills|news|agents|desk)\/[\d]{4}-[\d]{2}-[\d]{2}$/;
export default {
 async fetch(request,env){
  const url=new URL(request.url), path=url.pathname, bucket=env.BUCKET;
  if(path==='/' && request.method==='GET') return new Response(PAGE,{headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'}});
  if(!path.startsWith('/api/'))return json({error:'Unknown route'},404);
  if(request.method==='POST' && (request.headers.get('Origin') && request.headers.get('Origin')!==url.origin || !request.headers.get('Content-Type')?.startsWith('application/json')))return json({error:'Invalid request'},403);
  try{
   if(path==='/api/publish' && request.method==='POST'){
    // Owner-private Sites dispatch authenticates scheduled writers before this endpoint.
    const {room,date,title,body,excerpt=false}=await request.json(), id=room+'/'+date;
    if(!pattern.test(id)||!rooms.includes(room)||typeof title!=='string'||!title.trim()||title.length>220||typeof body!=='string'||!body.trim()||body.length>100000)return json({error:'Invalid post'},400);
    const post={id,room,date,title,body,excerpt:excerpt===true};
    await bucket.put('posts/'+date+'/'+room,JSON.stringify(post));
    return json({id});
   }
   if(path==='/api/post' && request.method==='GET'){
    const id=url.searchParams.get('id')||'';if(!pattern.test(id))return json({error:'Invalid id'},400);
    const [room,date]=id.split('/'), obj=await bucket.get('posts/'+date+'/'+room);return obj?json(await obj.json()):json({error:'Missing post'},404);
   }
   if(path==='/api/feed' && request.method==='GET'){
    let cursor,keys=[];do{const page=await bucket.list({prefix:'posts/',cursor});keys.push(...page.objects.map(o=>o.key));cursor=page.truncated?page.cursor:null;}while(cursor);
    const before=url.searchParams.get('before')||'',room=url.searchParams.get('room');
    keys=keys.filter(k=>(!before||k<before)&&(!room||k.endsWith('/'+room))).sort().reverse();
    const batch=keys.slice(0,20);const posts=await Promise.all(batch.map(async k=>(await bucket.get(k)).json()));
    return json({posts,next:keys.length>batch.length?batch.at(-1):null});
   }
   if(path==='/api/notebook'){
    const user=request.headers.get('oai-authenticated-user-id');if(!user)return json({error:'Sign in to save your work'},401);
    const id=url.searchParams.get('id')||'';if(!pattern.test(id))return json({error:'Invalid id'},400);
    const key='notebook/'+encodeURIComponent(user)+'/'+id;
    if(request.method==='GET'){const obj=await bucket.get(key);return json(obj?await obj.json():{saved:false,note:''});}
    if(request.method==='POST'){const {saved,note}=await request.json();if(typeof saved!=='boolean'||typeof note!=='string'||note.length>30000)return json({error:'Invalid note'},400);await bucket.put(key,JSON.stringify({saved,note}));return json({saved,note});}
   }
   return json({error:'Unsupported route'},404);
  }catch(err){return json({error:err instanceof SyntaxError?'Invalid JSON':'Storage unavailable'},err instanceof SyntaxError?400:503);}
 }
}
