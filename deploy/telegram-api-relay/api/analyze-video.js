function authorized(req) {
  const supplied=req.headers["x-relay-secret"];
  return typeof supplied==="string"&&supplied.length>=32&&supplied===process.env.RELAY_SECRET;
}

const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

export default async function handler(req,res){
  let uploadedName="";
  let stage="آماده‌سازی";
  const started=Date.now();
  const mark=value=>{stage=value;console.info("video_analysis_stage",{stage,elapsedMs:Date.now()-started});};
  try{
    if(!authorized(req))return res.status(401).json({error:{message:"Unauthorized"}});
    if(req.method!=="POST")return res.status(405).json({error:{message:"Method not allowed"}});
    const {fileId,sourceUrl,mimeType="video/mp4",topic="",promise=""}=req.body||{};
    if((typeof fileId!=="string"||fileId.length<10)&&typeof sourceUrl!=="string")return res.status(400).json({error:{message:"Invalid video source"}});
    const telegramToken=process.env.TELEGRAM_BOT_TOKEN,geminiKey=process.env.GEMINI_API_KEY;
    if(!telegramToken||!geminiKey)return res.status(503).json({error:{message:"Video analysis is not configured"}});
    let download;
    mark("دریافت فایل ویدئو");
    if(typeof sourceUrl==="string"){
      const source=new URL(sourceUrl);if(source.protocol!=="https:"||source.hostname!=="videobot.rafeie.ir")throw new Error("Video source is not allowed");
      download=await fetch(source,{signal:AbortSignal.timeout(120000)});
    }else{
      const fileMeta=await fetch(`https://api.telegram.org/bot${telegramToken}/getFile`,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({file_id:fileId})}).then(r=>r.json());
      if(!fileMeta.ok||!fileMeta.result?.file_path)throw new Error("Telegram file lookup failed");
      download=await fetch(`https://api.telegram.org/file/bot${telegramToken}/${fileMeta.result.file_path}`);
    }
    if(!download.ok)throw new Error(`Telegram file download failed: ${download.status}`);
    const bytes=Buffer.from(await download.arrayBuffer());
    if(bytes.length>500*1024*1024)throw new Error("Video is larger than 500 MB");
    mark("آپلود فایل در Gemini");
    const start=await fetch("https://generativelanguage.googleapis.com/upload/v1beta/files",{method:"POST",headers:{"x-goog-api-key":geminiKey,"content-type":"application/json","x-goog-upload-protocol":"resumable","x-goog-upload-command":"start","x-goog-upload-header-content-length":String(bytes.length),"x-goog-upload-header-content-type":mimeType},body:JSON.stringify({file:{display_name:`telegram-${Date.now()}`}}),signal:AbortSignal.timeout(20000)});
    const uploadUrl=start.headers.get("x-goog-upload-url");
    if(!start.ok||!uploadUrl)throw new Error(`Gemini upload start failed: ${start.status}`);
    let file=await fetch(uploadUrl,{method:"POST",headers:{"content-length":String(bytes.length),"x-goog-upload-offset":"0","x-goog-upload-command":"upload, finalize"},body:bytes}).then(async r=>{if(!r.ok)throw new Error(`Gemini upload failed: ${r.status}`);return r.json();});
    file=file.file||file; uploadedName=file.name||"";
    mark("آماده‌سازی ویدئو در Gemini");
    for(let i=0;file.state==="PROCESSING"&&i<24;i++){
      await sleep(3000);
      file=await fetch(`https://generativelanguage.googleapis.com/v1beta/${uploadedName}`,{headers:{"x-goog-api-key":geminiKey}}).then(r=>r.json());
    }
    if(file.state!=="ACTIVE")throw new Error(`Gemini video state: ${file.state||"unknown"}`);
    mark("بررسی مدل‌های در دسترس");
    const primary=process.env.GEMINI_VIDEO_MODEL||"gemini-3.8-flash";
    let available=[];
    try{
      const listed=await fetch("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",{headers:{"x-goog-api-key":geminiKey},signal:AbortSignal.timeout(10000)});
      if(listed.ok){const data=await listed.json();available=(data.models||[]).filter(m=>m.supportedGenerationMethods?.includes("generateContent")&&/gemini-.*flash/i.test(m.name)&&!/image|audio|tts|live|robotics/i.test(m.name)).map(m=>m.name.replace(/^models\//,""));}
    }catch{console.warn("video_analysis_model_discovery_failed");}
    const fallback=process.env.GEMINI_VIDEO_FALLBACK_MODEL;
    const alternatives=available.filter(m=>m!==primary).sort((a,b)=>Number(/2\.5/.test(a))-Number(/2\.5/.test(b))||Number(!/lite/.test(a))-Number(!/lite/.test(b))||b.localeCompare(a));
    const models=[...new Set([primary,...(fallback?[fallback]:[]),...alternatives])].slice(0,3);
    let analysis="",lastError;
    for(const model of models){
      mark(`تحلیل با مدل ${model}`);
      try{
        const generated=await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`,{method:"POST",headers:{"content-type":"application/json","x-goog-api-key":geminiKey},body:JSON.stringify({contents:[{parts:[{fileData:{mimeType,fileUri:file.uri}},{text:`این ویدئو را دقیق و واقع‌بینانه به فارسی تحلیل کن. موضوع اعلامی: ${topic}. وعده اعلامی: ${promise}. سوژه، گفتار و متن قابل مشاهده، ابزارها و مراحل آموزشی، ادعاها و CTA را خلاصه کن. چیزی که دیده یا شنیده نمی‌شود حدس نزن. حداکثر ۳۵۰ کلمه بنویس.`}]}],generationConfig:{temperature:.2,maxOutputTokens:2400}}),signal:AbortSignal.timeout(60000)});
        const json=await generated.json();
        if(!generated.ok)throw new Error(json?.error?.message||`Gemini generate failed: ${generated.status}`);
        analysis=json.candidates?.[0]?.content?.parts?.filter(p=>!p.thought)?.map(p=>p.text||"").join("").trim()||"";
        if(!analysis)throw new Error("Gemini returned no video analysis");
        break;
      }catch(error){lastError=error;console.warn("video_analysis_model_failed",{model,message:error instanceof Error?error.message:"unknown",elapsedMs:Date.now()-started});}
    }
    if(!analysis&&lastError)throw lastError;
    if(!analysis)throw new Error("Gemini returned no video analysis");
    return res.status(200).json({analysis});
  }catch(error){console.error("video_analysis_error",{stage,elapsedMs:Date.now()-started,message:error instanceof Error?error.message:"unknown"});return res.status(502).json({error:{message:`${stage}: ${error instanceof Error?error.message:"Video analysis failed"}`}});}
  finally{if(uploadedName){fetch(`https://generativelanguage.googleapis.com/v1beta/${uploadedName}`,{method:"DELETE",headers:{"x-goog-api-key":process.env.GEMINI_API_KEY||""}}).catch(()=>{});}}
}
