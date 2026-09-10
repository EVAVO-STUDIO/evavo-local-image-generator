"""Embedded MCP App control surface for EVAVO ComfyUI."""

COMFYUI_APP_URI = "ui://evavo/comfyui/v1.html"

COMFYUI_APP_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EVAVO ComfyUI</title>
<style>
:root{color-scheme:dark;--text:#f7f7f7;--muted:#a6a6ad;--panel:#16161a;--line:#303038;--accent:#ff244e;--ok:#44d17a}*{box-sizing:border-box}
body{margin:0;background:#0b0b0d;color:var(--text);font:14px/1.45 system-ui,sans-serif}main{max-width:920px;margin:auto;padding:18px}
header,.native{display:flex;align-items:center;justify-content:space-between;gap:14px}header{margin-bottom:14px}.brand{display:flex;align-items:center;gap:10px}
.mark{width:13px;height:36px;border-radius:3px;background:var(--accent);box-shadow:0 0 24px #ff244e66}h1{font-size:20px;margin:0}.sub,.tip,label{color:var(--muted)}
.sub{margin:2px 0 0}.status{display:flex;align-items:center;gap:8px;white-space:nowrap}.dot{width:9px;height:9px;border-radius:50%;background:#ffbe55}.dot.ok{background:var(--ok)}.dot.bad{background:var(--accent)}
.grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(260px,.65fr);gap:14px}.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:15px}.native{margin-bottom:14px}
label{display:block;font-size:12px;margin:0 0 6px}textarea,input{width:100%;border:1px solid var(--line);border-radius:9px;background:#0e0e11;color:var(--text);padding:10px;font:inherit;outline:none}
textarea:focus,input:focus{border-color:var(--accent)}textarea{min-height:118px;resize:vertical}.fields{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin-top:10px}
.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}button{border:1px solid var(--line);background:#24242a;color:var(--text);border-radius:9px;padding:9px 12px;font-weight:650;cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent)}button:disabled{opacity:.5;cursor:wait}.preview{min-height:245px;display:grid;place-items:center;overflow:hidden;background:#09090b;border:1px dashed var(--line);border-radius:10px}
.preview img{width:100%;height:auto;display:block}.empty{text-align:center;color:var(--muted);padding:20px}.log{margin-top:10px;padding:9px 10px;background:#0e0e11;border-radius:9px;color:var(--muted);min-height:40px;white-space:pre-wrap;word-break:break-word}
.tip{font-size:12px;margin:10px 0 0}@media(max-width:700px){.grid{grid-template-columns:1fr}.fields{grid-template-columns:1fr 1fr}}
</style></head><body><main>
<header><div class="brand"><span class="mark"></span><div><h1>EVAVO · ComfyUI</h1><p class="sub">Local GPU control, directly in this chat</p></div></div><div class="status"><span id="dot" class="dot"></span><span id="status">Connecting…</span></div></header>
<section class="native card"><div><strong>Native node editor</strong><div class="sub">Opens privately on the connected Windows workstation.</div></div><button id="openNative">Open full ComfyUI</button></section>
<div class="grid"><section class="card"><label for="prompt">Prompt</label><textarea id="prompt" placeholder="Describe the image you want…"></textarea>
<div class="fields"><div><label for="width">Width</label><input id="width" type="number" min="64" max="4096" step="64" value="1024"></div><div><label for="height">Height</label><input id="height" type="number" min="64" max="4096" step="64" value="1024"></div><div><label for="steps">Steps</label><input id="steps" type="number" min="1" max="150" value="24"></div></div>
<div class="actions"><button id="generate" class="primary">Generate image</button><button id="refresh">Check backend</button></div><div id="log" class="log">Ready for a prompt.</div><p class="tip">Generation stays on your machine. The MCP tunnel exposes tools—not private port 8188.</p></section>
<aside class="card"><label>Latest output</label><div id="preview" class="preview"><div class="empty">Your generated image will appear here.</div></div></aside></div>
</main><script>
(()=>{const $=id=>document.getElementById(id),pending=new Map();let callId=0;
const unpack=value=>{if(!value||typeof value!=="object")return{};if(value.structuredContent&&typeof value.structuredContent==="object")return value.structuredContent.result??value.structuredContent;if(value.result&&typeof value.result==="object"&&!Array.isArray(value.result))return value.result;return value};
function status(label,kind=""){$("status").textContent=String(label||"Unknown");$("dot").className="dot"+(kind?" "+kind:"")}
function log(value){const data=unpack(value),message=data.message||data.native_ui_warning||data.error_code;$("log").textContent=message?String(message):JSON.stringify(data,null,2)}
function opened(value){const data=unpack(value);status(data.ok?(data.native_ui_opened===false?"Ready in chat":"ComfyUI ready"):(data.status||"Start failed"),data.ok?"ok":"bad");log(data)}
function call(name,args={}){if(window.openai&&typeof window.openai.callTool==="function")return window.openai.callTool(name,args);return new Promise((resolve,reject)=>{const id="evavo-"+(++callId);pending.set(id,{resolve,reject});parent.postMessage({jsonrpc:"2.0",id,method:"tools/call",params:{name,arguments:args}},"*");setTimeout(()=>{if(pending.delete(id))reject(new Error("Chat tool call timed out"))},660000)})}
window.addEventListener("message",event=>{const msg=event.data;if(!msg||typeof msg!=="object")return;if(msg.id&&pending.has(msg.id)){const job=pending.get(msg.id);pending.delete(msg.id);msg.error?job.reject(new Error(msg.error.message||"Tool call failed")):job.resolve(msg.result);return}if(msg.method==="ui/notifications/tool-result")opened(msg.params)});
async function showImage(path){if(!path)return;const response=await call("read_output_image",{path}),content=response?.content||response?.result?.content||[],item=content.find(x=>x&&x.type==="image");if(!item||typeof item.data!=="string")return;const mime=/^image\/(?:png|jpeg|gif|webp)$/.test(item.mimeType||"")?item.mimeType:"image/png",node=document.createElement("img");node.alt="Generated image";node.src="data:"+mime+";base64,"+item.data;$("preview").replaceChildren(node)}
$("openNative").addEventListener("click",async()=>{const b=$("openNative");b.disabled=true;status("Opening…");try{opened(await call("open_comfyui_ui",{auto_start:true,wait_seconds:90}))}catch(e){status("Open failed","bad");log({message:e.message})}finally{b.disabled=false}});
$("refresh").addEventListener("click",async()=>{const b=$("refresh");b.disabled=true;status("Checking…");try{const r=unpack(await call("health_check",{}));status(r.ok===false?"Unavailable":"Backend ready",r.ok===false?"bad":"ok");log(r)}catch(e){status("Check failed","bad");log({message:e.message})}finally{b.disabled=false}});
$("generate").addEventListener("click",async()=>{const prompt=$("prompt").value.trim();if(!prompt){$("prompt").focus();log({message:"Enter a prompt first."});return}const b=$("generate");b.disabled=true;status("Generating…");$("log").textContent="Starting ComfyUI and generating locally…";try{const r=unpack(await call("generate_image",{prompt,project_name:"chatgpt",width:Number($("width").value),height:Number($("height").value),steps:Number($("steps").value),wait:true,auto_start:true}));status(r.ok===false?"Generation failed":"Complete",r.ok===false?"bad":"ok");log(r);const files=Array.isArray(r.downloaded_files)?r.downloaded_files:[];if(files[0])await showImage(String(files[0]))}catch(e){status("Generation failed","bad");log({message:e.message})}finally{b.disabled=false}});
if(window.openai?.toolOutput)opened(window.openai.toolOutput);else status("Control ready","ok")})();
</script></body></html>'''
