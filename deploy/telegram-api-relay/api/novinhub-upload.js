function authorized(req){const supplied=req.headers["x-relay-secret"];return typeof supplied==="string"&&supplied.length>=32&&supplied===process.env.RELAY_SECRET;}
async function callback(url,draftId,percent,label){if(!url)return;try{const target=new URL(url);if(target.protocol!=="https:"||target.hostname!=="videobot.rafeie.ir")return;await fetch(target,{method:"POST",headers:{"content-type":"application/json","x-relay-secret":process.env.RELAY_SECRET||""},body:JSON.stringify({draftId,percent,label}),signal:AbortSignal.timeout(15000)});}catch(error){console.error("progress_callback_error",error instanceof Error?error.message:"unknown");}}
function multipartStream(source,boundary,name,mime,onBytes){
  const safe=String(name).replace(/["\r\n]/g,"_").slice(0,180),encoder=new TextEncoder();
  const prefix=encoder.encode(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${safe}"\r\nContent-Type: ${mime}\r\n\r\n`),suffix=encoder.encode(`\r\n--${boundary}--\r\n`),reader=source.getReader();let stage=0;
  return {body:new ReadableStream({async pull(controller){if(stage===0){stage=1;controller.enqueue(prefix);return;}if(stage===1){const {done,value}=await reader.read();if(!done){onBytes(value.byteLength);controller.enqueue(value);return;}stage=2;}controller.enqueue(suffix);controller.close();},cancel(reason){return reader.cancel(reason);}}),overhead:prefix.byteLength+suffix.byteLength};
}
export default async function handler(req,res){
  try{
    if(!authorized(req))return res.status(401).json({error:{message:"Unauthorized"}});
    if(req.method!=="POST")return res.status(405).json({error:{message:"Method not allowed"}});
    const {fileId,sourceUrl,name="video.mp4",mime="video/mp4",callbackUrl,draftId=""}=req.body||{};
    if((typeof fileId!=="string"||fileId.length<10)&&typeof sourceUrl!=="string")return res.status(400).json({error:{message:"Invalid video source"}});
    const telegramToken=process.env.TELEGRAM_BOT_TOKEN,novinhubToken=process.env.NOVINHUB_API_TOKEN;
    if(!telegramToken||!novinhubToken)return res.status(503).json({error:{message:"Relay upload is not configured"}});
    await callback(callbackUrl,draftId,20,"Vercel درخواست ویدئو را دریافت کرد");
    let download;
    if(typeof sourceUrl==="string"){const source=new URL(sourceUrl);if(source.protocol!=="https:"||source.hostname!=="videobot.rafeie.ir")throw new Error("Video source is not allowed");download=await fetch(source,{signal:AbortSignal.timeout(180000)});}
    else {const meta=await fetch(`https://api.telegram.org/bot${telegramToken}/getFile`,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({file_id:fileId}),signal:AbortSignal.timeout(30000)}).then(r=>r.json());if(!meta.ok||!meta.result?.file_path)throw new Error(meta.description||"Telegram file lookup failed");download=await fetch(`https://api.telegram.org/file/bot${telegramToken}/${meta.result.file_path}`,{signal:AbortSignal.timeout(180000)});}
    if(!download.ok||!download.body)throw new Error(`Video source download failed: ${download.status}`);
    const total=Number(download.headers.get("content-length")||0);if(total>500*1024*1024)throw new Error("Video is larger than 500 MB");
    const boundary=`rafiei-${crypto.randomUUID()}`;let received=0,lastReported=0;const stream=multipartStream(download.body,boundary,name,mime,count=>{received+=count;if(received>500*1024*1024)throw new Error("Video is larger than 500 MB");const percent=total?Math.floor(received/total*100):0;if(percent>=lastReported+10){lastReported=percent;void callback(callbackUrl,draftId,Math.min(70,45+Math.floor(percent*.25)),`انتقال مستقیم به Novinhub: ${percent}٪`);}});
    await callback(callbackUrl,draftId,45,total?`انتقال مستقیم ${Math.ceil(total/1024/1024)} مگابایت به Novinhub شروع شد`:"انتقال مستقیم ویدئو به Novinhub شروع شد");
    const headers={Authorization:`Bearer ${novinhubToken}`,"content-type":`multipart/form-data; boundary=${boundary}`};if(total)headers["content-length"]=String(total+stream.overhead);
    const upstream=await fetch("https://api.novinhub.com/token/v2/file",{method:"POST",headers,body:stream.body,duplex:"half",signal:AbortSignal.timeout(285000)});
    const json=await upstream.json().catch(()=>({}));if(!upstream.ok||!json.id)throw new Error(json?.error?.message||json?.message||`Novinhub upload failed: ${upstream.status}`);
    await callback(callbackUrl,draftId,72,"شناسه فایل Novinhub دریافت شد");return res.status(200).json({id:Number(json.id)});
  }catch(error){console.error("novinhub_upload_error",error instanceof Error?error.message:"unknown");return res.status(502).json({error:{message:error instanceof Error?error.message:"Upload failed"}});}
}
