"use strict";

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const uid = () => crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
const clamp = (value, low, high) => Math.max(low, Math.min(high, Number(value) || 0));
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const formatTime = seconds => {
  seconds = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(seconds / 3600), minutes = Math.floor(seconds % 3600 / 60), secs = Math.floor(seconds % 60), frames = Math.floor(seconds % 1 * project.fps);
  return [hours, minutes, secs].map(value => String(value).padStart(2,"0")).join(":") + "." + String(frames).padStart(2,"0");
};
const FILTER_PRESETS = [
  {id:"none",name:"None",description:"Original image"},
  {id:"cinematic",name:"Cinematic",description:"Balanced teal and warmth"},
  {id:"warm",name:"Warm",description:"Golden highlights"},
  {id:"cool",name:"Cool",description:"Clean blue tone"},
  {id:"vintage",name:"Vintage",description:"Faded film color"},
  {id:"mono",name:"Mono",description:"Neutral black and white"},
  {id:"noir",name:"Noir",description:"High-contrast monochrome"},
  {id:"vivid",name:"Vivid",description:"Punchy color"},
  {id:"soft",name:"Soft",description:"Gentle low contrast"},
  {id:"teal_orange",name:"Teal & Orange",description:"Stylized split tone"},
];
const filterPreset = id => FILTER_PRESETS.find(item=>item.id===id)||FILTER_PRESETS[0];
const defaultClip = media => ({
  id: uid(), file: media.file, name: media.name, kind: media.kind === "image" ? "freeze" : "video",
  track: 0, timelineStart: 0, start: 0, end: media.duration || 3, duration: media.kind === "image" ? 3 : undefined,
  speed: 1, reverse: false, transition: "none", transitionDuration: .5,
  volume: 1, mute: false, brightness: 0, contrast: 1, saturation: 1, gamma: 1,
  temperature: 0, tint: 0, hue: 0, shadows: 0, highlights: 0, lut: "", filter: "none", filterIntensity: 1,
  crop: {x:0,y:0,w:1,h:1}, zoom: 1, focusX: .5, focusY: .5, scale: .45,
  positionX: .5, positionY: .5, rotation: 0, mirrorH: false, mirrorV: false,
  stabilize: false, stabilizeStrength: 12, opacity: 1, anchorText: "", tracking: null,
  keyframes: {}, audioDetached: false
});
const defaultAudioClip = (media,start=0,duration=0) => ({
  id:uid(),file:media.file,name:media.name||media.file,start:Math.max(0,Number(start)||0),
  duration:Math.max(.05,Number(duration)||Number(media.duration)||3),sourceStart:0,
  speed:1,reverse:false,volume:1,mute:false,linkedClipId:""
});
const freshProject = () => ({
  version: "1.2.0-beta.1", name: "Untitled project", ratio: "16:9", fps: 30, title: "", watermark: "",
  watermarkOpacity: .55, imageWatermark: {file:"",opacity:.7,scale:.2,x:.8,y:.08}, safeArea: false,
  clips: [], audioClips: [], audio: "", musicVolume: .5, voiceovers: [], audioDucking: true,
  export: {container:"mp4",codec:"h264",width:"",height:"",quality:20,hardware:true,pcmAudio:false}
});

let project = freshProject();
let media = [], recent = [], selectedClipId = "", selectedAudioClipId = "", selectedVoiceoverId = "", selectedMediaFile = "", libraryView = "project", inspectorTab = "clip";
let history = [], future = [], playheadTime = 0, isPlayingTimeline = false, saveTimer, toastTimer, waveformCache = new Map();
let audioContext, previewSource, previewGain, recorder, recordChunks = [], recordStart = 0;
let suppressTimelineClick = false;
const proxyRequests = new Map();
const preview = $("#preview"), stillPreview = $("#stillPreview"), stage = $("#stage");

function snapshot(pushHistory=true){
  if(pushHistory){ history.push(JSON.stringify(project)); if(history.length>60) history.shift(); future=[]; }
  clearTimeout(saveTimer); $("#saveState").textContent="Saving…";
  saveTimer=setTimeout(()=>{localStorage.setItem("vdodesk.autosave",JSON.stringify({project,media,at:Date.now()}));$("#saveState").textContent="Recovered locally";},350);
}
function restore(serialized){
  const incoming=typeof serialized==="string"?JSON.parse(serialized):serialized;
  const value=incoming.project||incoming;
  project={...freshProject(),...value,imageWatermark:{...freshProject().imageWatermark,...(value.imageWatermark||{})},export:{...freshProject().export,...(value.export||{})}};
  project.clips=(value.clips||[]).map(clip=>({...defaultClip({file:clip.file,name:clip.name||clip.file,kind:clip.kind==="freeze"?"image":"video",duration:clip.end||3}),...clip,crop:{x:0,y:0,w:1,h:1,...(clip.crop||{})},keyframes:{...(clip.keyframes||{})}}));
  project.audioClips=(value.audioClips||[]).map(item=>({...defaultAudioClip({file:item.file,name:item.name||item.file,duration:item.duration},item.start,item.duration),...item}));
  project.voiceovers=value.voiceovers||[]; selectedClipId=project.clips[0]?.id||"";selectedAudioClipId="";selectedVoiceoverId=""; renderAll();
}
function toast(message){const node=$("#toast");node.textContent=message;node.classList.add("show");clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.classList.remove("show"),2600);}
function selectedClip(){return project.clips.find(clip=>clip.id===selectedClipId);}
function selectedAudioClip(){return project.audioClips.find(clip=>clip.id===selectedAudioClipId);}
function selectedVoiceover(){return project.voiceovers.find(voice=>voice.id===selectedVoiceoverId);}
function mediaByFile(file){return [...media,...recent].find(item=>item.file===file)||{file,name:file,url:"/media/"+encodeURIComponent(file),duration:0,kind:"video"};}
function highlightedAudio(){return [...media,...recent].find(item=>item.file===selectedMediaFile&&item.kind==="audio");}
function primaryClips(){return project.clips.filter(clip=>Number(clip.track)===0);}
function durationOf(clip){return clip.kind==="freeze"?clamp(clip.duration,.1,3600):Math.max(.05,(Number(clip.end)-Number(clip.start))/clamp(clip.speed,.25,4));}
function timelineLayout(){
  let cursor=0; const map=new Map();
  for(const clip of primaryClips()){
    const overlap=clip.transition!=="none"?Math.min(Number(clip.transitionDuration)||.5,durationOf(clip)/2,cursor/2):0;
    const start=Math.max(0,cursor-overlap); map.set(clip.id,{start,duration:durationOf(clip)}); cursor=start+durationOf(clip);
  }
  for(const clip of project.clips.filter(item=>Number(item.track)>0)) map.set(clip.id,{start:Number(clip.timelineStart)||0,duration:durationOf(clip)});
  for(const audio of project.audioClips) map.set(audio.id,{start:Number(audio.start)||0,duration:Math.max(.05,Number(audio.duration)||.05)});
  for(const voice of project.voiceovers) map.set(voice.id,{start:Number(voice.start)||0,duration:Number(voice.duration)||3});
  const total=Math.max(cursor,...[...map.values()].map(item=>item.start+item.duration),1);
  return {map,total};
}
function pushChange(mutator){snapshot(true);mutator();renderAll();}
function rememberUndoState(){history.push(JSON.stringify(project));if(history.length>60)history.shift();future=[];}

async function api(path, options={}){
  const response=await fetch(path,options); const value=await response.json();
  if(!response.ok) throw new Error(value.error||"Request failed"); return value;
}
async function refreshRecent(){try{recent=(await api("/api/recent")).items||[]; if(libraryView==="recent")renderLibrary();}catch(error){toast(error.message)}}
async function refreshWorkspaceMedia(){
  const workspace=(await api("/api/media")).items||[],byFile=new Map([...media,...workspace].map(item=>[item.file,item]));
  media=[...byFile.values()].sort((a,b)=>String(b.importedAt||"").localeCompare(String(a.importedAt||"")));
  return workspace;
}
const wait=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
function preparePreviewProxy(file,autoplay=false){
  if(proxyRequests.has(file))return proxyRequests.get(file);
  const task=(async()=>{
    toast("Preparing a browser-compatible preview…");
    await api("/api/proxy",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({file})});
    for(let attempt=0;attempt<300;attempt++){
      await wait(1000);
      const workspace=await refreshWorkspaceMedia(),item=workspace.find(value=>value.file===file);
      if(item?.proxy){
        renderLibrary();
        if(selectedClip()?.file===file){
          loadSelectedPreview(true);
          toast("Preview ready");
          if(autoplay){
            const resume=()=>{if(!isPlayingTimeline&&selectedClip()?.file===file)togglePlay()};
            if(preview.readyState>=1)resume();else preview.addEventListener("loadedmetadata",resume,{once:true});
          }
        }
        return item;
      }
      if(item&&!item.proxyPending&&attempt>1)throw new Error("FFmpeg could not create the preview proxy");
    }
    throw new Error("Preview proxy timed out");
  })().catch(error=>toast(`Preview unavailable: ${error.message}`)).finally(()=>proxyRequests.delete(file));
  proxyRequests.set(file,task);return task;
}
async function uploadFile(file){
  toast(`Importing ${file.name}…`);
  const item=await api("/api/upload",{method:"POST",headers:{"X-Filename":file.name,"Content-Type":"application/octet-stream"},body:file});
  media=media.filter(value=>value.file!==item.file);media.unshift(item);selectedMediaFile=item.file;await refreshRecent();renderLibrary();renderInspector();toast(`${file.name} imported`);return item;
}
async function importFiles(files){for(const file of files){try{await uploadFile(file)}catch(error){toast(`${file.name}: ${error.message}`)}}snapshot(false);}
function addMediaToTimeline(item){
  if(item.kind==="audio"){
    const available=Math.max(.05,timelineLayout().total-playheadTime),audio=defaultAudioClip(item,playheadTime,Math.min(Number(item.duration)||available,available));
    pushChange(()=>project.audioClips.push(audio));selectedAudioClipId=audio.id;selectedVoiceoverId="";inspectorTab="audio";renderAll();toast("Added music to A1");return;
  }
  if(item.kind==="lut"){const clip=selectedClip();if(clip)pushChange(()=>clip.lut=item.file);else toast("Select a clip before applying a LUT");return;}
  const clip=defaultClip(item); if(item.kind==="image"){clip.track=1;clip.timelineStart=playheadTime;clip.scale=.35;}
  pushChange(()=>project.clips.push(clip));selectedClipId=clip.id;selectedAudioClipId="";selectedVoiceoverId="";renderAll();seekTimeline(timelineLayout().map.get(clip.id)?.start||0);toast("Added to timeline");
}

function renderLibrary(){
  const list=libraryView==="recent"?recent:media;
  $("#mediaList").innerHTML=list.length?list.map(item=>`<div class="media-card ${selectedMediaFile===item.file?"selected":""}" data-media="${escapeHtml(item.file)}">
    <div class="media-icon">${item.kind==="audio"?"♫":item.kind==="image"?"▧":item.kind==="lut"?"◈":"▶"}</div><div><div class="name">${escapeHtml(item.name)}</div><small>${item.kind}${item.duration?` · ${item.duration.toFixed(1)}s`:""}${item.proxy?" · proxy":item.proxyPending?" · preparing preview":""}</small></div><button class="add" data-add="${escapeHtml(item.file)}">＋</button></div>`).join(""):`<div class="empty">${libraryView==="recent"?"No recent files":"Import media to begin"}</div>`;
}
function renderTimeline(){
  const {map,total}=timelineLayout(), scale=Number($("#timelineZoom").value); document.documentElement.style.setProperty("--scale",`${scale}px`);
  const width=Math.max(650,total*scale+120); $("#ruler").style.width=`${width}px`; $("#tracks").style.width=`${width+58}px`;
  $("#ruler").innerHTML=Array.from({length:Math.ceil(total)+2},(_,i)=>`<span style="left:${i*scale+3}px">${formatTime(i).slice(3,8)}</span>`).join("");
  const rows=[{track:2,label:"V3"},{track:1,label:"V2"},{track:0,label:"V1"},{track:"audio",label:"A1"},{track:"voice",label:"VO"}];
  $("#tracks").innerHTML=rows.map(row=>`<div class="track" data-track="${row.track}"><div class="track-label">${row.label}</div><div class="track-lane">${timelineItems(row.track,map,scale)}</div></div>`).join("");
  $("#playhead").style.left=`${58+playheadTime*scale}px`; $("#playhead").style.height=`${24+rows.length*42}px`;
  $("#timelineSummary").textContent=`${project.clips.length} clips · ${total.toFixed(1)}s`;
  requestAnimationFrame(drawWaveforms);
}
function timelineItems(track,map,scale){
  if(track==="audio") return primaryClips().filter(clip=>!clip.audioDetached&&mediaByFile(clip.file).hasAudio!==false).map(clip=>linkedAudioHtml(clip,map.get(clip.id),scale)).join("")+project.audioClips.map(audio=>audioClipHtml(audio,map.get(audio.id),scale)).join("")+(project.audio?`<div class="clip audio legacy-audio" style="left:0;width:${Math.max(20,timelineLayout().total*scale)}px"><span class="clip-name">♫ Legacy music · ${escapeHtml(mediaByFile(project.audio).name)}</span></div>`:"");
  if(track==="voice") return project.voiceovers.map(voice=>voiceHtml(voice,map.get(voice.id),scale)).join("");
  return project.clips.filter(clip=>Number(clip.track)===Number(track)).map(clip=>clipHtml(clip,map.get(clip.id),scale,Number(track)>0?"overlay":"")).join("");
}
function linkedAudioHtml(clip,layout,scale){return `<div class="clip audio linked-audio ${selectedClipId===clip.id&&inspectorTab==="audio"&&!selectedAudioClipId?"selected":""}" data-linked-audio="${clip.id}" title="Linked to ${escapeHtml(clip.name)} — unlink it to edit independently" style="left:${layout.start*scale}px;width:${Math.max(20,layout.duration*scale)}px"><canvas class="waveform" data-waveform="${escapeHtml(clip.file)}"></canvas><span class="clip-name">🔗 ${clip.mute?"Muted · ":""}${escapeHtml(clip.name)}</span></div>`;}
function audioClipHtml(audio,layout,scale){return `<div class="clip audio ${selectedAudioClipId===audio.id?"selected":""}" data-audio-clip="${audio.id}" title="Drag to move this independent audio clip" style="left:${layout.start*scale}px;width:${Math.max(20,layout.duration*scale)}px"><canvas class="waveform" data-waveform="${escapeHtml(audio.file)}"></canvas><span class="trim left"></span><span class="clip-name">♫ ${audio.mute?"Muted · ":""}${escapeHtml(audio.name)}</span><span class="trim right"></span></div>`;}
function clipHtml(clip,layout,scale,kind){
  const transition=clip.transition!=="none"?`<span class="transition-badge">${escapeHtml(clip.transition)}</span>`:"";
  const sequence=Number(clip.track)===0?primaryClips().findIndex(item=>item.id===clip.id)+1:0;
  const preset=filterPreset(clip.filter),filterBadge=preset.id!=="none"?`<span class="filter-badge">${escapeHtml(preset.name)}</span>`:"";
  return `<div class="clip ${kind} ${selectedClipId===clip.id?"selected":""}" data-clip="${clip.id}" title="${sequence?"Drag horizontally to rearrange this sequence":"Drag to position overlay"}" style="left:${layout.start*scale}px;width:${Math.max(20,layout.duration*scale)}px"><canvas class="waveform" data-waveform="${escapeHtml(clip.file)}"></canvas><span class="trim left"></span><span class="clip-name">${sequence?`<span class="sequence-number">${sequence}</span>`:""}${escapeHtml(clip.name)}</span>${transition}${filterBadge}<span class="trim right"></span></div>`;
}
function voiceHtml(voice,layout,scale){return `<div class="clip voice ${selectedVoiceoverId===voice.id?"selected":""}" data-voice="${voice.id}" style="left:${layout.start*scale}px;width:${Math.max(20,layout.duration*scale)}px"><span class="clip-name">● ${escapeHtml(voice.name||"Voiceover")}</span></div>`;}
async function drawWaveforms(){
  for(const canvas of $$("canvas.waveform")){
    const file=canvas.dataset.waveform;if(!file)continue; const rect=canvas.getBoundingClientRect();canvas.width=Math.max(1,rect.width*devicePixelRatio);canvas.height=Math.max(1,rect.height*devicePixelRatio);
    let peaks=waveformCache.get(file);if(!peaks){try{peaks=(await api(`/api/waveform/${encodeURIComponent(file)}?points=240`)).peaks;waveformCache.set(file,peaks)}catch{peaks=[]}}
    const ctx=canvas.getContext("2d");ctx.strokeStyle="#62dba3";ctx.lineWidth=devicePixelRatio;ctx.beginPath();peaks.forEach((peak,i)=>{const x=i/(peaks.length-1)*canvas.width,h=peak*canvas.height*.44;ctx.moveTo(x,canvas.height/2-h);ctx.lineTo(x,canvas.height/2+h)});ctx.stroke();
  }
}

const rangeField=(label,prop,min,max,step,value,unit="")=>`<div class="field range"><label>${label}</label><input type="range" data-prop="${prop}" min="${min}" max="${max}" step="${step}" value="${value}"><output>${Number(value).toFixed(step<1?2:0)}${unit}</output></div>`;
const inputField=(label,prop,value,type="number",attrs="")=>`<div class="field"><label>${label}</label><input type="${type}" data-prop="${prop}" value="${escapeHtml(value)}" ${attrs}></div>`;
const checkField=(label,prop,value)=>`<label class="check"><input type="checkbox" data-prop="${prop}" ${value?"checked":""}> ${label}</label>`;
function renderInspector(){
  $$("#inspectorTabs button").forEach(button=>button.classList.toggle("active",button.dataset.tab===inspectorTab));
  const clip=selectedClip(),audioClip=selectedAudioClip(),voice=selectedVoiceover(),music=highlightedAudio();
  $("#selectionLabel").textContent=audioClip&&inspectorTab==="audio"?(audioClip.name||"Audio"):voice&&inspectorTab==="audio"?(voice.name||"Voiceover"):clip?clip.name:"Project";
  const body=$("#inspectorBody");
  const voiceSection=voice?`<div class="section"><h3>Selected voiceover</h3>${rangeField("Voice level","voice.volume",0,4,.01,voice.volume??1,"×")}${inputField("Timeline start","voice.start",voice.start??0,"number",'min="0" step=".01"')}<button data-action="remove-voice" class="danger">Remove selected voiceover</button></div>`:"";
  const musicHint=music?`Highlighted music: <strong>${escapeHtml(music.name)}</strong>`:"Highlight an audio file in Media before replacing.";
  if(inspectorTab==="audio"&&audioClip){
    const linked=project.clips.find(item=>item.id===audioClip.linkedClipId);
    body.innerHTML=`<div class="section"><h3>Independent A1 audio</h3><div class="notice">This audio can move, trim, mute, replace, or delete without changing the video.</div>${rangeField("Level","audio.volume",0,4,.01,audioClip.volume??1,"×")}${checkField("Mute audio","audio.mute",audioClip.mute)}${inputField("Timeline start","audio.start",audioClip.start??0,"number",'min="0" step=".01"')}${inputField("Duration","audio.duration",audioClip.duration??3,"number",'min=".05" step=".01"')}<p class="hint">${musicHint}</p><div class="row"><button data-action="replace-selected-audio" ${music?"":"disabled"}>Replace with highlighted music</button><button data-action="delete-audio" class="danger">Delete audio only</button></div>${linked?'<button data-action="restore-original-audio">Restore original linked audio</button>':""}</div><div class="section"><h3>Voice mix</h3>${checkField("Duck A1 audio under voiceover","project.audioDucking",project.audioDucking)}</div>`;
    body.querySelectorAll("input[data-prop],select[data-prop]").forEach(control=>{control.addEventListener("input",inspectorInput);control.addEventListener("change",inspectorChange)});return;
  }
  if(inspectorTab!=="project"&&!clip){if(inspectorTab==="audio"&&voice){body.innerHTML=voiceSection;body.querySelectorAll("input[data-prop],select[data-prop]").forEach(control=>{control.addEventListener("input",inspectorInput);control.addEventListener("change",inspectorChange)});return}body.innerHTML='<div class="empty">Select a timeline clip</div>';return;}
  if(inspectorTab==="clip") body.innerHTML=`<div class="section"><h3>Timing</h3>${inputField("Source in","start",clip.start,"number",'min="0" step=".01"')}${inputField("Source out","end",clip.end,"number",'min=".05" step=".01"')}${clip.kind==="freeze"?inputField("Still duration","duration",clip.duration||3,"number",'min=".1" step=".1"'):""}${rangeField("Speed","speed",.25,4,.05,clip.speed,"×")}${checkField("Reverse clip","reverse",clip.reverse)}</div><div class="section"><h3>Track & transition</h3><div class="field"><label>Video track</label><select data-prop="track"><option value="0" ${clip.track==0?"selected":""}>V1 · primary</option><option value="1" ${clip.track==1?"selected":""}>V2 · overlay</option><option value="2" ${clip.track==2?"selected":""}>V3 · overlay</option></select></div>${Number(clip.track)>0?inputField("Timeline start","timelineStart",clip.timelineStart,"number",'min="0" step=".01"'):""}<div class="field"><label>Transition in</label><select data-prop="transition">${["none","dissolve","fade","wipe","slide","zoom"].map(v=>`<option ${clip.transition===v?"selected":""}>${v}</option>`).join("")}</select></div>${rangeField("Transition","transitionDuration",.04,3,.01,clip.transitionDuration,"s")}</div>`;
  else if(inspectorTab==="transform") body.innerHTML=`<div class="section"><h3>Position & framing</h3>${rangeField("Zoom","zoom",1,8,.01,clip.zoom,"×")}${rangeField("Focus X","focusX",0,1,.01,clip.focusX)}${rangeField("Focus Y","focusY",0,1,.01,clip.focusY)}${Number(clip.track)>0?rangeField("Overlay scale","scale",.05,1,.01,clip.scale):""}${Number(clip.track)>0?rangeField("Position X","positionX",0,1,.01,clip.positionX):""}${Number(clip.track)>0?rangeField("Position Y","positionY",0,1,.01,clip.positionY):""}${rangeField("Rotation","rotation",-180,180,1,clip.rotation,"°")}${checkField("Mirror horizontally","mirrorH",clip.mirrorH)}${checkField("Mirror vertically","mirrorV",clip.mirrorV)}${rangeField("Opacity","opacity",0,1,.01,clip.opacity)}</div><div class="section"><h3>Crop (normalized)</h3>${rangeField("Left","crop.x",0,.95,.01,clip.crop.x)}${rangeField("Top","crop.y",0,.95,.01,clip.crop.y)}${rangeField("Width","crop.w",.05,1,.01,clip.crop.w)}${rangeField("Height","crop.h",.05,1,.01,clip.crop.h)}</div><div class="section"><h3>Stabilization</h3>${checkField("Enable stabilization","stabilize",clip.stabilize)}${rangeField("Strength","stabilizeStrength",4,32,1,clip.stabilizeStrength)}</div>`;
  else if(inspectorTab==="color") body.innerHTML=`<div class="section"><h3>Primary correction</h3>${rangeField("Brightness","brightness",-1,1,.01,clip.brightness)}${rangeField("Contrast","contrast",.1,4,.01,clip.contrast)}${rangeField("Saturation","saturation",0,4,.01,clip.saturation)}${rangeField("Gamma","gamma",.1,4,.01,clip.gamma)}</div><div class="section"><h3>Color balance</h3>${rangeField("Temperature","temperature",-100,100,1,clip.temperature)}${rangeField("Tint","tint",-100,100,1,clip.tint)}${rangeField("Hue","hue",-180,180,1,clip.hue,"°")}${rangeField("Shadows","shadows",-100,100,1,clip.shadows)}${rangeField("Highlights","highlights",-100,100,1,clip.highlights)}<div class="field"><label>3D LUT</label><select data-prop="lut"><option value="">None</option>${media.filter(i=>i.kind==="lut").map(i=>`<option value="${escapeHtml(i.file)}" ${clip.lut===i.file?"selected":""}>${escapeHtml(i.name)}</option>`).join("")}</select></div><button data-action="reset-color">Reset color</button></div>`;
  else if(inspectorTab==="motion") body.innerHTML=`<div class="notice">Start values come from Transform/Color. End values animate linearly across the clip.</div><div class="section"><h3>End keyframe</h3>${rangeField("End zoom","keyframes.zoomEnd",1,8,.01,clip.keyframes.zoomEnd??clip.zoom,"×")}${rangeField("End focus X","keyframes.focusXEnd",0,1,.01,clip.keyframes.focusXEnd??clip.focusX)}${rangeField("End focus Y","keyframes.focusYEnd",0,1,.01,clip.keyframes.focusYEnd??clip.focusY)}${rangeField("End brightness","keyframes.brightnessEnd",-1,1,.01,clip.keyframes.brightnessEnd??clip.brightness)}${rangeField("End contrast","keyframes.contrastEnd",.1,4,.01,clip.keyframes.contrastEnd??clip.contrast)}${rangeField("End saturation","keyframes.saturationEnd",0,4,.01,clip.keyframes.saturationEnd??clip.saturation)}${rangeField("End gamma","keyframes.gammaEnd",.1,4,.01,clip.keyframes.gammaEnd??clip.gamma)}<button data-action="clear-keyframes">Clear keyframes</button></div>`;
  else if(inspectorTab==="audio") body.innerHTML=`${voiceSection}<div class="section"><h3>Video clip audio</h3>${clip.audioDetached?'<div class="notice">Original audio is unlinked. The video stays silent until you restore it; its independent audio is on A1 if it has not been deleted.</div>':'<div class="notice">Linked audio follows this video. Unlink it to edit or delete audio without changing the picture.</div>'}${rangeField("Level","volume",0,4,.01,clip.volume,"×")}${checkField("Mute clip audio","mute",clip.mute)}${rangeField("End level","keyframes.volumeEnd",0,4,.01,clip.keyframes.volumeEnd??clip.volume,"×")}<p class="hint">${musicHint}</p><div class="row">${clip.audioDetached?'<button data-action="restore-original-audio">Restore original audio</button>':'<button data-action="unlink-audio">Unlink audio to A1</button>'}<button data-action="replace-selected-audio" ${music?"":"disabled"}>Replace with highlighted music</button></div></div><div class="section"><h3>Voice mix</h3>${checkField("Duck A1 audio under voiceover","project.audioDucking",project.audioDucking)}${project.audio?`${rangeField("Legacy music level","project.musicVolume",0,4,.01,project.musicVolume,"×")}<button data-action="clear-music">Remove legacy music</button>`:""}</div>`;
  else if(inspectorTab==="ai"){
    const tracking=clip.tracking||{};body.innerHTML=`<div class="section"><h3>Subject tracking & mask</h3><div class="notice">Analyze through the clip, then correct the first-frame box manually if needed. The tracked path drives smart reframe and anchored text.</div><button data-action="analyze">Track subject</button> <button data-action="manual-track">Use manual box</button>${tracking.engine?`<p class="hint">${escapeHtml(tracking.engine)}${tracking.path?.length?` · ${tracking.path.length} samples`:""}</p>`:""}${rangeField("Box X","tracking.box.x",0,1,.01,tracking.box?.x??.2)}${rangeField("Box Y","tracking.box.y",0,1,.01,tracking.box?.y??.15)}${rangeField("Box width","tracking.box.w",.05,1,.01,tracking.box?.w??.6)}${rangeField("Box height","tracking.box.h",.05,1,.01,tracking.box?.h??.7)}${checkField("Draw tracked object outline","tracking.outline",tracking.outline)}<button data-action="smart-reframe">Smart reframe</button>${inputField("Anchored text","anchorText",clip.anchorText,"text",'maxlength="120"')} ${tracking.maskUrl?'<label class="check"><input id="showMask" type="checkbox"> Preview segmentation mask</label>':""}</div>`;
  } else body.innerHTML=projectInspector();
  if(inspectorTab==="clip"&&Number(clip.track)===0){
    const sequence=primaryClips(),position=sequence.findIndex(item=>item.id===clip.id)+1;
    body.insertAdjacentHTML("afterbegin",`<div class="section"><h3>Video sequence</h3><div class="notice">Clip ${position} of ${sequence.length}. Drag it along V1 or use the buttons to change playback order.</div><div class="row"><button data-action="move-earlier" ${position<=1?"disabled":""}>← Move earlier</button><button data-action="move-later" ${position>=sequence.length?"disabled":""}>Move later →</button></div></div>`);
  }
  if(inspectorTab==="filters"){
    const selected=filterPreset(clip.filter);
    body.innerHTML=`<div class="section"><h3>Clip filter</h3><div class="notice">Filters apply only to the selected clip and are included in preview renders and final exports.</div><div class="filter-grid">${FILTER_PRESETS.map(preset=>`<button class="filter-preset filter-${preset.id} ${selected.id===preset.id?"active":""}" data-filter="${preset.id}"><strong>${escapeHtml(preset.name)}</strong><small>${escapeHtml(preset.description)}</small></button>`).join("")}</div></div><div class="section"><h3>Filter strength</h3>${rangeField("Intensity","filterIntensity",0,1,.01,clip.filterIntensity??1)}<button data-action="reset-filter">Remove filter</button></div>`;
  }
  body.querySelectorAll("input[data-prop],select[data-prop]").forEach(control=>{control.addEventListener("input",inspectorInput);control.addEventListener("change",inspectorChange)});
  applyPreviewEffects();
}
function projectInspector(){return `<div class="section"><h3>Canvas</h3><div class="field"><label>Aspect ratio</label><select data-project="ratio">${["16:9","9:16","4:3","3:4","1:1"].map(v=>`<option ${project.ratio===v?"selected":""}>${v}</option>`).join("")}</select></div><div class="field"><label>Frame rate</label><select data-project="fps">${[24,25,30,50,60].map(v=>`<option ${project.fps==v?"selected":""}>${v}</option>`).join("")}</select></div>${checkField("Show safe-area guides","project.safeArea",project.safeArea)}</div><div class="section"><h3>Titles</h3>${inputField("Opening title","project.title",project.title,"text",'maxlength="300"')}${inputField("Text watermark","project.watermark",project.watermark,"text",'maxlength="120"')}${rangeField("Watermark opacity","project.watermarkOpacity",0,1,.01,project.watermarkOpacity)}</div><div class="section"><h3>Image watermark</h3><div class="field"><label>Image</label><select data-project="imageWatermark.file"><option value="">None</option>${media.filter(i=>i.kind==="image").map(i=>`<option value="${escapeHtml(i.file)}" ${project.imageWatermark.file===i.file?"selected":""}>${escapeHtml(i.name)}</option>`).join("")}</select></div>${rangeField("Scale","project.imageWatermark.scale",.03,1,.01,project.imageWatermark.scale)}${rangeField("Opacity","project.imageWatermark.opacity",0,1,.01,project.imageWatermark.opacity)}${rangeField("Position X","project.imageWatermark.x",0,1,.01,project.imageWatermark.x)}${rangeField("Position Y","project.imageWatermark.y",0,1,.01,project.imageWatermark.y)}<p class="hint">You can also drag the watermark in the viewer.</p></div><div class="section"><h3>Recovery</h3><button data-action="recover">Restore last autosave</button> <button data-action="recover-previous">Restore previous project</button> <button data-action="clear-recovery">Clear recovery</button></div>`;}
function setNested(target,path,value){const keys=path.split(".");let node=target;for(const key of keys.slice(0,-1)){node[key]??={};node=node[key]}node[keys.at(-1)]=value;}
function beginControlEdit(control){if(control.dataset.undoCaptured)return;rememberUndoState();control.dataset.undoCaptured="1";}
function inspectorInput(event){
  const control=event.currentTarget,path=control.dataset.prop; let value=control.type==="checkbox"?control.checked:control.type==="range"||control.type==="number"?Number(control.value):control.value;
  beginControlEdit(control);
  if(path.startsWith("project."))setNested(project,path.slice(8),value);
  else if(path.startsWith("voice.")){const voice=selectedVoiceover();if(voice)setNested(voice,path.slice(6),value);}
  else if(path.startsWith("audio.")){const audio=selectedAudioClip();if(audio)setNested(audio,path.slice(6),value);}
  else setNested(selectedClip(),path,value);
  const clip=selectedClip();if(clip&&path.startsWith("crop.")){clip.crop.x=clamp(clip.crop.x,0,.95);clip.crop.y=clamp(clip.crop.y,0,.95);clip.crop.w=clamp(clip.crop.w,.05,1-clip.crop.x);clip.crop.h=clamp(clip.crop.h,.05,1-clip.crop.y);}
  const output=control.nextElementSibling;if(output?.tagName==="OUTPUT")output.textContent=`${Number(value).toFixed(Number(control.step)<1?2:0)}${output.textContent.replace(/[-\d.]/g,"")}`;
  snapshot(false);applyPreviewEffects();renderTimeline();
}
function inspectorChange(event){if(!event.currentTarget.dataset.undoCaptured)inspectorInput(event);delete event.currentTarget.dataset.undoCaptured;renderInspector();}

function previewFilterCss(id,intensity){
  const i=clamp(intensity,0,1);
  if(!i||id==="none")return "";
  if(id==="cinematic")return ` contrast(${1+.14*i}) saturate(${1+.08*i}) sepia(${.08*i}) hue-rotate(${-10*i}deg)`;
  if(id==="warm")return ` brightness(${1+.03*i}) saturate(${1+.10*i}) sepia(${.22*i}) hue-rotate(${-12*i}deg)`;
  if(id==="cool")return ` contrast(${1+.05*i}) sepia(${.12*i}) hue-rotate(${175*i}deg) saturate(${1+.06*i})`;
  if(id==="vintage")return ` sepia(${.42*i}) saturate(${1-.28*i}) contrast(${1-.07*i}) brightness(${1+.04*i})`;
  if(id==="mono")return ` grayscale(${i})`;
  if(id==="noir")return ` grayscale(${i}) contrast(${1+.42*i}) brightness(${1-.07*i})`;
  if(id==="vivid")return ` saturate(${1+.55*i}) contrast(${1+.12*i})`;
  if(id==="soft")return ` contrast(${1-.12*i}) saturate(${1-.08*i}) brightness(${1+.06*i})`;
  if(id==="teal_orange")return ` sepia(${.18*i}) hue-rotate(${150*i}deg) saturate(${1+.24*i}) contrast(${1+.08*i})`;
  return "";
}

function applyPreviewEffects(){
  const clip=selectedClip(); const imageMode=clip?.kind==="freeze"; preview.style.display=imageMode?"none":"block";stillPreview.style.display=imageMode?"block":"none";
  if(clip){
    const progress=clip.kind==="freeze"?0:clamp((preview.currentTime-clip.start)/Math.max(.05,clip.end-clip.start),0,1),mix=(start,end)=>Number(start)+(Number(end??start)-Number(start))*progress;
    const rawBrightness=1+mix(clip.brightness,clip.keyframes?.brightnessEnd),rawContrast=mix(clip.contrast,clip.keyframes?.contrastEnd),saturation=mix(clip.saturation,clip.keyframes?.saturationEnd),gamma=mix(clip.gamma,clip.keyframes?.gammaEnd),hue=Number(clip.hue),temp=Number(clip.temperature),tint=Number(clip.tint),shadows=Number(clip.shadows),highlights=Number(clip.highlights),zoom=mix(clip.zoom,clip.keyframes?.zoomEnd),focusX=mix(clip.focusX,clip.keyframes?.focusXEnd),focusY=mix(clip.focusY,clip.keyframes?.focusYEnd);
    // CSS is an intentionally responsive approximation; the FFmpeg renderer is
    // authoritative. Every inspector control still produces an immediate and
    // visible preview response instead of appearing inert.
    const brightness=clamp(rawBrightness*(1+(gamma-1)*.22+(shadows+highlights)/900),.05,4),contrast=clamp(rawContrast*(1+(highlights-shadows)/700),.05,5),colorStrength=clamp((Math.abs(temp)+Math.abs(tint))/260,0,.7),colorAngle=hue+(temp<0?185:-12)+(tint>=0?-35:75);
    const filter=`brightness(${brightness}) contrast(${contrast}) saturate(${saturation}) sepia(${colorStrength}) hue-rotate(${colorStrength?colorAngle:hue}deg)${previewFilterCss(clip.filter,clip.filterIntensity??1)}`;
    const sx=clip.mirrorH?-1:1,sy=clip.mirrorV?-1:1,overlay=Number(clip.track)>0,baseScale=overlay?Number(clip.scale):1;const transform=`scale(${sx*zoom*baseScale},${sy*zoom*baseScale}) rotate(${clip.rotation}deg)`;
    const crop=clip.crop||{x:0,y:0,w:1,h:1},clipPath=`inset(${clamp(crop.y,0,1)*100}% ${clamp(1-crop.x-crop.w,0,1)*100}% ${clamp(1-crop.y-crop.h,0,1)*100}% ${clamp(crop.x,0,1)*100}%)`;
    for(const element of [preview,stillPreview]){element.style.filter=filter;element.style.transform=transform;element.style.transformOrigin=`${focusX*100}% ${focusY*100}%`;element.style.opacity=clip.opacity;element.style.clipPath=clipPath;element.style.left=overlay?`${(clip.positionX-.5)*100}%`:"0";element.style.top=overlay?`${(clip.positionY-.5)*100}%`:"0";}
    const tracking=clip.tracking;const box=$("#subjectBox");box.style.display=tracking?.box?"block":"none";if(tracking?.box){Object.assign(box.style,{left:`${tracking.box.x*100}%`,top:`${tracking.box.y*100}%`,width:`${tracking.box.w*100}%`,height:`${tracking.box.h*100}%`})}
    const anchor=$("#anchorOverlay");anchor.textContent=clip.anchorText||"";anchor.style.display=clip.anchorText?"block":"none";anchor.style.left=`${(tracking?.focus?.x??clip.focusX)*100}%`;anchor.style.top=`${(tracking?.focus?.y??clip.focusY)*100}%`;
    if(previewGain)previewGain.gain.value=clip.mute?0:mix(clip.volume,clip.keyframes?.volumeEnd);
  }
  $("#titleOverlay").textContent=project.title;$("#titleOverlay").style.display=project.title?"block":"none";$("#textWatermark").textContent=project.watermark;$("#textWatermark").style.opacity=project.watermarkOpacity;
  $("#safeArea").style.display=project.safeArea?"block":"none"; stage.className=`stage ratio-${project.ratio.replace(":","-")}`;
  const wm=$("#imageWatermark"),conf=project.imageWatermark,item=mediaByFile(conf.file);wm.style.display=conf.file?"block":"none";if(conf.file)wm.src=item.url;Object.assign(wm.style,{width:`${conf.scale*100}%`,opacity:conf.opacity,left:`${conf.x*100}%`,top:`${conf.y*100}%`});
  const mask=$("#maskPreview"),maskToggle=$("#showMask");mask.style.display=maskToggle?.checked&&clip?.tracking?.maskUrl?"block":"none";if(clip?.tracking?.maskUrl)mask.src=clip.tracking.maskUrl;
}
function renderAll(){
  $("#projectName").value=project.name;renderLibrary();renderTimeline();renderInspector();loadSelectedPreview(false);updateTimecode();
}
function loadSelectedPreview(seek=true){
  const clip=selectedClip();if(!clip){preview.removeAttribute("src");stillPreview.removeAttribute("src");return}const item=mediaByFile(clip.file);const url=$("#proxyToggle").checked&&item.proxy?item.proxy:item.url;
  if(clip.kind==="freeze"){if(stillPreview.src!==new URL(item.url,location.href).href)stillPreview.src=item.url;applyPreviewEffects();return}
  if($("#proxyToggle").checked&&!item.proxy&&(item.proxyPending||item.browserPlayable===false))preparePreviewProxy(clip.file,false);
  const absolute=new URL(url,location.href).href;if(preview.src!==absolute){preview.src=url;preview.load();preview.onloadedmetadata=()=>{if(seek)preview.currentTime=clip.start;applyPreviewEffects();};}else if(seek)preview.currentTime=clip.start;
  applyPreviewEffects();
}
function seekTimeline(time){
  const {map,total}=timelineLayout();playheadTime=clamp(time,0,total);let target=project.clips.find(clip=>{const item=map.get(clip.id);return item&&playheadTime>=item.start&&playheadTime<item.start+item.duration});
  if(!target)target=primaryClips().at(-1)||project.clips.at(-1);if(target&&target.id!==selectedClipId){selectedClipId=target.id;renderInspector();loadSelectedPreview(false)}
  if(target&&target.kind!=="freeze"){const item=map.get(target.id);preview.currentTime=Number(target.start)+(playheadTime-item.start)*Number(target.speed||1)}
  renderTimeline();updateTimecode();
}
function updateTimecode(){const total=timelineLayout().total;$("#timecode").textContent=`${formatTime(playheadTime)} / ${formatTime(total)}`;}
function setupAudio(){if(audioContext)return;const Context=window.AudioContext||window.webkitAudioContext;if(!Context)return;audioContext=new Context();previewSource=audioContext.createMediaElementSource(preview);previewGain=audioContext.createGain();previewSource.connect(previewGain).connect(audioContext.destination);applyPreviewEffects();}
async function togglePlay(){
  const clip=selectedClip();if(!clip)return;setupAudio();if(audioContext)await audioContext.resume();
  if(isPlayingTimeline){preview.pause();isPlayingTimeline=false;$("#playButton").textContent="▶";return}
  try{
    isPlayingTimeline=true;$("#playButton").textContent="❚❚";if(clip.kind!=="freeze")preview.playbackRate=clip.speed;if(clip.kind!=="freeze")await preview.play();
    requestAnimationFrame(playTick);
  }catch(error){
    isPlayingTimeline=false;$("#playButton").textContent="▶";
    const item=mediaByFile(clip.file),usingProxy=preview.currentSrc.includes("/proxies/");
    if($("#proxyToggle").checked&&!usingProxy)preparePreviewProxy(clip.file,true);else toast(`Preview cannot play: ${error.message}`);
  }
}
function playTick(){
  if(!isPlayingTimeline)return;const clip=selectedClip(),layout=clip&&timelineLayout().map.get(clip.id);if(!clip||!layout){isPlayingTimeline=false;return}
  if(clip.kind!=="freeze")playheadTime=layout.start+(preview.currentTime-clip.start)/clip.speed;else playheadTime+=1/60;
  if(playheadTime>=layout.start+layout.duration-.02){const map=timelineLayout().map,all=primaryClips().map(item=>[item.id,map.get(item.id)]).filter(([,item])=>item).sort((a,b)=>a[1].start-b[1].start),next=all.find(([,item])=>item.start>layout.start+.001);if(next){selectedClipId=next[0];selectedVoiceoverId="";playheadTime=next[1].start;renderInspector();loadSelectedPreview(true);const nc=selectedClip();if(nc?.kind!=="freeze"){preview.playbackRate=nc.speed;preview.play().catch(()=>{})}}else{isPlayingTimeline=false;$("#playButton").textContent="▶";}}
  renderTimeline();updateTimecode();if(isPlayingTimeline)requestAnimationFrame(playTick);
}

function movePrimaryClip(clip,offset){
  if(!clip||Number(clip.track)!==0)return toast("Select a clip on the V1 sequence");
  const sequence=primaryClips(),from=sequence.indexOf(clip),to=from+offset;
  if(to<0||to>=sequence.length)return toast(offset<0?"Clip is already first":"Clip is already last");
  const other=sequence[to],fromIndex=project.clips.indexOf(clip),toIndex=project.clips.indexOf(other);
  pushChange(()=>{[project.clips[fromIndex],project.clips[toIndex]]=[project.clips[toIndex],project.clips[fromIndex]]});
  const layout=timelineLayout().map.get(clip.id);if(layout)seekTimeline(layout.start);
  toast(`Moved to sequence position ${to+1}`);
}

function unlinkClipAudio(clip){
  if(!clip)return null;
  const existing=project.audioClips.find(audio=>audio.linkedClipId===clip.id);
  if(existing)return existing;
  const layout=timelineLayout().map.get(clip.id),item=mediaByFile(clip.file);
  if(item.hasAudio===false)return null;
  const audio=defaultAudioClip({file:clip.file,name:`${clip.name} audio`,duration:layout?.duration},layout?.start||0,layout?.duration||durationOf(clip));
  const clipVolume=Number.isFinite(Number(clip.volume))?Number(clip.volume):1;
  Object.assign(audio,{sourceStart:Number(clip.start)||0,speed:Number(clip.speed)||1,reverse:Boolean(clip.reverse),volume:clipVolume,linkedClipId:clip.id});
  clip.audioBeforeDetach={mute:Boolean(clip.mute),volume:clipVolume};clip.audioDetached=true;clip.mute=true;project.audioClips.push(audio);return audio;
}
function replaceSelectedAudio(){
  const music=highlightedAudio();if(!music)return toast("Highlight an audio file in Media first");
  let audio=selectedAudioClip(),clip=selectedClip();
  if(!audio&&(!clip||mediaByFile(clip.file).hasAudio===false))return toast("Select an A1 audio clip or a video clip with audio");
  snapshot(true);
  if(!audio&&clip)audio=unlinkClipAudio(clip);
  if(!audio)return toast("Select an A1 audio clip or a video clip with audio");
  Object.assign(audio,{file:music.file,name:music.name,sourceStart:0,speed:1,reverse:false,mute:false});
  selectedAudioClipId=audio.id;selectedVoiceoverId="";inspectorTab="audio";renderAll();toast("Audio replaced on A1; video was not changed");
}
function restoreOriginalAudio(){
  const audio=selectedAudioClip(),clip=audio?.linkedClipId?project.clips.find(item=>item.id===audio.linkedClipId):selectedClip();
  if(!clip)return toast("The original video clip is no longer available");
  pushChange(()=>{project.audioClips=project.audioClips.filter(item=>item.linkedClipId!==clip.id);clip.audioDetached=false;clip.mute=Boolean(clip.audioBeforeDetach?.mute);if(clip.audioBeforeDetach?.volume!=null)clip.volume=clip.audioBeforeDetach.volume;delete clip.audioBeforeDetach;selectedAudioClipId="";selectedClipId=clip.id});
  toast("Original video audio restored");
}

function action(name){
  const clip=selectedClip(),audioClip=selectedAudioClip(),layout=clip&&timelineLayout().map.get(clip.id);
  if(name==="import")return $("#mediaFiles").click();
  if(name==="new"){if(!confirm("Start a new project? The current project will be kept as the previous recovery snapshot."))return;const current=localStorage.getItem("vdodesk.autosave")||JSON.stringify({project,media,at:Date.now()});localStorage.setItem("vdodesk.recovery.previous",current);history=[];future=[];project=freshProject();selectedClipId="";selectedAudioClipId="";selectedVoiceoverId="";snapshot(false);renderAll();return}
  if(name==="save")return saveProject(); if(name==="open")return $("#projectFile").click(); if(name==="export")return openExportDialog(); if(name==="preview")return startRender(true);
  if(name==="undo"&&history.length){future.push(JSON.stringify(project));restore(history.pop());snapshot(false);return}if(name==="redo"&&future.length){history.push(JSON.stringify(project));restore(future.pop());snapshot(false);return}
  if(name==="play")return togglePlay();if(name==="timeline-start")return seekTimeline(0);if(name==="timeline-end")return seekTimeline(timelineLayout().total-1/project.fps);if(name==="clip-start"&&layout)return seekTimeline(layout.start);if(name==="clip-end"&&layout)return seekTimeline(layout.start+layout.duration-1/project.fps);if(name==="step-back")return seekTimeline(playheadTime-1/project.fps);if(name==="step-forward")return seekTimeline(playheadTime+1/project.fps);
  if(name==="delete"&&audioClip)return action("delete-audio");
  if(name==="delete"&&clip)return pushChange(()=>{project.clips=project.clips.filter(c=>c.id!==clip.id);selectedClipId=project.clips[0]?.id||""});
  if(name==="duplicate"&&clip)return pushChange(()=>{const copy=structuredClone(clip);copy.id=uid();copy.name+=" copy";if(copy.track>0)copy.timelineStart+=.25;project.clips.splice(project.clips.indexOf(clip)+1,0,copy);selectedClipId=copy.id});
  if(name==="move-earlier")return movePrimaryClip(clip,-1);if(name==="move-later")return movePrimaryClip(clip,1);
  if(name==="split"&&clip&&clip.kind!=="freeze"&&layout){const sourceAt=clip.start+(playheadTime-layout.start)*clip.speed;if(sourceAt<=clip.start+.05||sourceAt>=clip.end-.05)return toast("Move the playhead inside the selected clip");pushChange(()=>{const copy=structuredClone(clip);copy.id=uid();copy.start=sourceAt;copy.name+=" B";clip.end=sourceAt;project.clips.splice(project.clips.indexOf(clip)+1,0,copy);selectedClipId=copy.id});return}
  if(name==="freeze"&&clip)return createFreeze(clip);if(name==="record")return toggleRecording();if(name==="relink")return selectedMediaFile?$("#relinkFile").click():toast("Select a media file first");
  if(name==="unlink-audio"&&clip){if(mediaByFile(clip.file).hasAudio===false)return toast("This clip has no audio stream");snapshot(true);const audio=unlinkClipAudio(clip);if(!audio)return toast("This clip has no audio stream");selectedAudioClipId=audio.id;selectedVoiceoverId="";inspectorTab="audio";renderAll();toast("Audio unlinked to A1");return}
  if(name==="replace-selected-audio")return replaceSelectedAudio();
  if(name==="delete-audio"&&audioClip){pushChange(()=>{project.audioClips=project.audioClips.filter(item=>item.id!==audioClip.id);selectedAudioClipId=""});toast("Audio deleted; video kept");return}
  if(name==="restore-original-audio")return restoreOriginalAudio();
  if(name==="remove-voice"&&selectedVoiceoverId)return pushChange(()=>{project.voiceovers=project.voiceovers.filter(voice=>voice.id!==selectedVoiceoverId);selectedVoiceoverId=""});
  if(name==="reset-color"&&clip)return pushChange(()=>Object.assign(clip,{brightness:0,contrast:1,saturation:1,gamma:1,temperature:0,tint:0,hue:0,shadows:0,highlights:0,lut:""}));
  if(name==="reset-filter"&&clip)return pushChange(()=>Object.assign(clip,{filter:"none",filterIntensity:1}));
  if(name==="clear-keyframes"&&clip)return pushChange(()=>clip.keyframes={});if(name==="clear-music")return pushChange(()=>project.audio="");
  if(name==="analyze"&&clip)return analyze(clip,false);if(name==="manual-track"&&clip)return analyze(clip,true);if(name==="smart-reframe"&&clip){if(!clip.tracking?.focus)return toast("Analyze or define a subject first");return pushChange(()=>{const path=clip.tracking.path||[],first=path[0]||clip.tracking.focus,last=path.at(-1)||first;clip.focusX=first.x;clip.focusY=first.y;clip.zoom=Math.max(1,Math.min(3,.72/Math.max(clip.tracking.box.w,clip.tracking.box.h)));clip.keyframes.focusXEnd=last.x;clip.keyframes.focusYEnd=last.y;clip.keyframes.zoomEnd=clip.zoom});}
  if(name==="recover"){const saved=localStorage.getItem("vdodesk.autosave");saved?restore(saved):toast("No recovery snapshot found");return}if(name==="recover-previous"){const saved=localStorage.getItem("vdodesk.recovery.previous");saved?restore(saved):toast("No previous-project snapshot found");return}if(name==="clear-recovery"){localStorage.removeItem("vdodesk.autosave");localStorage.removeItem("vdodesk.recovery.previous");toast("Recovery snapshots cleared");return}
}
async function createFreeze(clip){try{const item=await api("/api/freeze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({file:clip.file,at:preview.currentTime||clip.start})});media.unshift(item);const freeze=defaultClip(item);freeze.kind="freeze";freeze.duration=3;freeze.end=3;const index=project.clips.indexOf(clip);snapshot(true);project.clips.splice(index+1,0,freeze);selectedClipId=freeze.id;renderAll();toast("Freeze frame inserted")}catch(error){toast(error.message)}}
async function analyze(clip,manual){try{toast("Tracking subject through clip…");const box=manual?(clip.tracking?.box||{x:.2,y:.15,w:.6,h:.7}):undefined;const result=await api("/api/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({file:clip.file,at:preview.currentTime||clip.start,end:clip.end,manualBox:box})});snapshot(true);clip.tracking={...result,outline:clip.tracking?.outline||false};renderInspector();applyPreviewEffects();toast(result.engine)}catch(error){toast(error.message)}}
function saveProject(){project.name=$("#projectName").value||"Untitled project";const blob=new Blob([JSON.stringify(project,null,2)],{type:"application/json"});const link=document.createElement("a");link.href=URL.createObjectURL(blob);link.download=project.name.replace(/[^\w -]/g,"_")+".vdodesk.json";link.click();URL.revokeObjectURL(link.href);$("#saveState").textContent="Project downloaded";}
function syncExportOptions(){const webm=$("#exportContainer").value==="webm",codec=$("#exportCodec");if(webm)codec.value="vp9";else if(codec.value==="vp9")codec.value="h264";[...codec.options].forEach(option=>option.disabled=webm?option.value!=="vp9":option.value==="vp9");$("#pcmAudio").disabled=$("#exportContainer").value!=="mov";if($("#pcmAudio").disabled)$("#pcmAudio").checked=false;}
function openExportDialog(){const settings=project.export||{};$("#exportContainer").value=settings.container||"mp4";$("#exportCodec").value=settings.codec||"h264";$("#exportWidth").value=settings.width||"";$("#exportHeight").value=settings.height||"";$("#exportQuality").value=settings.quality??20;$("#hardwareExport").checked=settings.hardware!==false;$("#pcmAudio").checked=Boolean(settings.pcmAudio);syncExportOptions();$("#exportDialog").showModal();}
async function startRender(previewMode=false){
  if(!project.clips.length)return toast("Add at least one clip");$("#exportDialog").close();toast(previewMode?"Rendering preview…":"Export started…");
  try{const {job}=await api(previewMode?"/api/preview":"/api/render",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(project)});pollJob(job,previewMode)}catch(error){toast(error.message)}
}
async function pollJob(job,previewMode){try{const state=await api(`/api/job/${job}`);toast(`${state.message}${state.progress?` · ${state.progress}%`:""}`);if(state.state==="done"){if(previewMode){preview.src=state.url;preview.play().catch(error=>toast(`Preview could not start: ${error.message}`));}else{const link=document.createElement("a");link.href=state.url;link.download="";link.click();}const warnings=state.details?.warnings||[];if(warnings.length)toast(`Export ready · ${warnings.join(" ")}`);return}if(state.state==="error")return;setTimeout(()=>pollJob(job,previewMode),900)}catch(error){toast(error.message)}}
async function toggleRecording(){
  if(recorder?.state==="recording"){recorder.stop();return}
  try{const stream=await navigator.mediaDevices.getUserMedia({audio:true});recordChunks=[];recorder=new MediaRecorder(stream);recordStart=playheadTime;recorder.ondataavailable=e=>recordChunks.push(e.data);recorder.onstop=async()=>{stream.getTracks().forEach(track=>track.stop());$("#recordButton").classList.remove("recording");$("#recordButton").textContent="● Voiceover";try{const blob=new Blob(recordChunks,{type:recorder.mimeType});const file=new File([blob],`voiceover-${Date.now()}.webm`,{type:blob.type});const item=await uploadFile(file);const duration=await blobDuration(blob),voice={id:uid(),file:item.file,name:item.name,start:recordStart,duration,volume:1};snapshot(true);project.voiceovers.push(voice);selectedAudioClipId="";selectedVoiceoverId=voice.id;inspectorTab="audio";renderAll();toast("Voiceover added with automatic ducking")}catch(error){toast(error.message)}};recorder.start();$("#recordButton").classList.add("recording");$("#recordButton").textContent="■ Stop recording";toast("Recording voiceover…")}catch(error){toast(`Microphone unavailable: ${error.message}`)}
}
function blobDuration(blob){return new Promise(resolve=>{const audio=document.createElement("audio");audio.preload="metadata";audio.onloadedmetadata=()=>{URL.revokeObjectURL(audio.src);resolve(Number.isFinite(audio.duration)?audio.duration:3)};audio.src=URL.createObjectURL(blob)});}

document.addEventListener("click",event=>{
  if(suppressTimelineClick){suppressTimelineClick=false;event.preventDefault();return}
  const actionNode=event.target.closest("[data-action]");if(actionNode){event.preventDefault();action(actionNode.dataset.action);return}
  const filterNode=event.target.closest("[data-filter]");if(filterNode){event.preventDefault();const clip=selectedClip();if(clip)pushChange(()=>{clip.filter=filterNode.dataset.filter;clip.filterIntensity=clip.filterIntensity??1});return}
  const add=event.target.closest("[data-add]");if(add){event.stopPropagation();addMediaToTimeline(mediaByFile(add.dataset.add));return}
  const card=event.target.closest("[data-media]");if(card){selectedMediaFile=card.dataset.media;renderLibrary();renderInspector();return}
  const audioNode=event.target.closest("[data-audio-clip]");if(audioNode){selectedAudioClipId=audioNode.dataset.audioClip;selectedVoiceoverId="";inspectorTab="audio";playheadTime=Number(selectedAudioClip()?.start)||0;renderTimeline();renderInspector();updateTimecode();return}
  const linkedAudioNode=event.target.closest("[data-linked-audio]");if(linkedAudioNode){selectedClipId=linkedAudioNode.dataset.linkedAudio;selectedAudioClipId="";selectedVoiceoverId="";inspectorTab="audio";const item=timelineLayout().map.get(selectedClipId);playheadTime=item?.start||0;renderTimeline();renderInspector();updateTimecode();return}
  const voiceNode=event.target.closest("[data-voice]");if(voiceNode){selectedAudioClipId="";selectedVoiceoverId=voiceNode.dataset.voice;inspectorTab="audio";playheadTime=Number(selectedVoiceover()?.start)||0;renderTimeline();renderInspector();updateTimecode();return}
  const clipNode=event.target.closest("[data-clip]");if(clipNode){selectedClipId=clipNode.dataset.clip;selectedAudioClipId="";selectedVoiceoverId="";const item=timelineLayout().map.get(selectedClipId);seekTimeline(item.start);renderAll();return}
});
$("#inspectorTabs").addEventListener("click",event=>{const button=event.target.closest("[data-tab]");if(button){inspectorTab=button.dataset.tab;renderInspector()}});
$$('[data-library]').forEach(button=>button.addEventListener("click",()=>{libraryView=button.dataset.library;$$('[data-library]').forEach(b=>b.classList.toggle("active",b===button));renderLibrary()}));
$("#mediaFiles").addEventListener("change",event=>importFiles(event.target.files));
$("#projectFile").addEventListener("change",async event=>{try{restore(await event.target.files[0].text());snapshot(false);toast("Project opened") }catch(error){toast(`Invalid project: ${error.message}`)}});
$("#relinkFile").addEventListener("change",async event=>{try{const old=selectedMediaFile,item=await uploadFile(event.target.files[0]);snapshot(true);project.clips.filter(c=>c.file===old).forEach(c=>{c.file=item.file;c.name=item.name});project.audioClips.filter(c=>c.file===old).forEach(c=>{c.file=item.file;c.name=item.name});project.voiceovers.filter(c=>c.file===old).forEach(c=>c.file=item.file);if(project.audio===old)project.audio=item.file;if(project.imageWatermark.file===old)project.imageWatermark.file=item.file;selectedMediaFile=item.file;renderAll();toast("All project references relinked")}catch(error){toast(error.message)}});
$("#projectName").addEventListener("input",event=>{project.name=event.target.value;snapshot(false)});
$("#timelineZoom").addEventListener("input",renderTimeline);$("#proxyToggle").addEventListener("change",()=>loadSelectedPreview(false));
$("#inspectorBody").addEventListener("change",event=>{if(event.target.matches("[data-project]")){rememberUndoState();const value=event.target.type==="checkbox"?event.target.checked:event.target.dataset.project==="fps"?Number(event.target.value):event.target.value;setNested(project,event.target.dataset.project,value);snapshot(false);renderAll()}if(event.target.id==="showMask")applyPreviewEffects()});
$("#exportContainer").addEventListener("change",syncExportOptions);
$("#startExport").addEventListener("click",event=>{event.preventDefault();project.export={container:$("#exportContainer").value,codec:$("#exportCodec").value,width:$("#exportWidth").value,height:$("#exportHeight").value,quality:Number($("#exportQuality").value),hardware:$("#hardwareExport").checked,pcmAudio:$("#pcmAudio").checked};snapshot(false);startRender(false)});
preview.addEventListener("timeupdate",()=>{applyPreviewEffects();if(!isPlayingTimeline){const clip=selectedClip(),layout=clip&&timelineLayout().map.get(clip.id);if(layout){playheadTime=layout.start+(preview.currentTime-clip.start)/clip.speed;updateTimecode();$("#playhead").style.left=`${58+playheadTime*Number($("#timelineZoom").value)}px`}}});
preview.addEventListener("ended",()=>{if(isPlayingTimeline)playTick()});
preview.addEventListener("error",()=>{const clip=selectedClip();if(!clip||!preview.currentSrc)return;if(preview.currentSrc.includes("/proxies/"))toast("The preview proxy could not be decoded");else if($("#proxyToggle").checked)preparePreviewProxy(clip.file,false);});
const timelineScroll=$(".timeline-scroll");let timelineScrubbing=false;
function scrubTimelinePointer(event){const lane=timelineScroll.getBoundingClientRect(),scroll=timelineScroll.scrollLeft;seekTimeline((event.clientX-lane.left+scroll-58)/Number($("#timelineZoom").value));}
timelineScroll.addEventListener("pointerdown",event=>{if(event.target.closest(".clip"))return;timelineScrubbing=true;if(isPlayingTimeline){preview.pause();isPlayingTimeline=false;$("#playButton").textContent="▶";}timelineScroll.setPointerCapture(event.pointerId);scrubTimelinePointer(event);event.preventDefault()});
timelineScroll.addEventListener("pointermove",event=>{if(timelineScrubbing)scrubTimelinePointer(event)});
timelineScroll.addEventListener("pointerup",event=>{if(timelineScrubbing&&timelineScroll.hasPointerCapture(event.pointerId))timelineScroll.releasePointerCapture(event.pointerId);timelineScrubbing=false});
timelineScroll.addEventListener("pointercancel",()=>{timelineScrubbing=false});

let dragState=null;
const tracks=$("#tracks");
function videoTrackAtPoint(x,y){
  const track=document.elementFromPoint(x,y)?.closest("[data-track]");
  return track&&["0","1","2"].includes(track.dataset.track)?track:null;
}
function audioTrackAtPoint(x,y){const track=document.elementFromPoint(x,y)?.closest('[data-track="audio"]');return track||null;}
function timelineTimeAtPoint(x,track){
  const lane=track.querySelector(".track-lane").getBoundingClientRect();
  return Math.max(0,(x-lane.left)/Number($("#timelineZoom").value));
}
function primaryDropIndex(clip,time){
  const others=primaryClips().filter(item=>item!==clip),layout=timelineLayout().map;
  const index=others.findIndex(item=>time<(layout.get(item)?.start||0)+durationOf(item)/2);
  return index<0?others.length:index;
}
function moveClipToPrimaryIndex(clip,index){
  const remaining=project.clips.filter(item=>item!==clip),sequence=remaining.filter(item=>Number(item.track)===0);
  const target=Math.max(0,Math.min(sequence.length,index));clip.track=0;clip.timelineStart=0;
  let absolute;
  if(target<sequence.length)absolute=remaining.indexOf(sequence[target]);
  else if(sequence.length)absolute=remaining.indexOf(sequence.at(-1))+1;
  else absolute=0;
  remaining.splice(absolute,0,clip);project.clips=remaining;
}
function beginTimelineChange(){
  if(!dragState||dragState.changed)return;
  history.push(dragState.beforeProject);if(history.length>60)history.shift();future=[];dragState.changed=true;
}
function clearTimelineDropTarget(){
  $$(".track.drop-target").forEach(node=>node.classList.remove("drop-target"));
  $("#timelineDropIndicator")?.remove();
}
function clearTimelineDropUI(){
  clearTimelineDropTarget();
  if(dragState?.node){dragState.node.classList.remove("dragging");dragState.node.style.transform=""}
}
function showTimelineDropUI(event,target){
  $$(".track.drop-target").forEach(node=>node.classList.toggle("drop-target",node===target));
  let marker=$("#timelineDropIndicator");if(!marker){marker=document.createElement("i");marker.id="timelineDropIndicator";marker.className="timeline-drop-indicator"}
  const lane=target.querySelector(".track-lane"),rect=lane.getBoundingClientRect();lane.append(marker);
  marker.style.left=`${Math.max(0,Math.min(rect.width,event.clientX-rect.left))}px`;
}
function restoreDraggedClip(){
  const clip=dragState.clip||dragState.audioClip,original=dragState.original;
  Object.keys(clip).forEach(key=>delete clip[key]);Object.assign(clip,structuredClone(original));
}
tracks.addEventListener("pointerdown",event=>{
  const audioNode=event.target.closest("[data-audio-clip]");
  if(audioNode){
    const audioClip=project.audioClips.find(item=>item.id===audioNode.dataset.audioClip);if(!audioClip)return;
    const side=event.target.classList.contains("left")?"left":event.target.classList.contains("right")?"right":"move",trackNode=audioNode.closest("[data-track]"),layout=timelineLayout().map.get(audioClip.id),pointerTime=timelineTimeAtPoint(event.clientX,trackNode);
    selectedAudioClipId=audioClip.id;selectedVoiceoverId="";inspectorTab="audio";
    dragState={audioClip,node:audioNode,startX:event.clientX,startY:event.clientY,original:structuredClone(audioClip),beforeProject:JSON.stringify(project),side,pointerId:event.pointerId,moved:false,changed:false,grabOffset:Math.max(0,pointerTime-(layout?.start||0))};
    tracks.setPointerCapture(event.pointerId);if(side==="move")audioNode.classList.add("dragging");event.preventDefault();return;
  }
  const clipNode=event.target.closest("[data-clip]");if(!clipNode)return;
  const sourceTrack=clipNode.closest("[data-track]")?.dataset.track;
  if(sourceTrack==="audio")return toast("Drag the corresponding video clip on V1");
  const clip=project.clips.find(c=>c.id===clipNode.dataset.clip);if(!clip)return;
  const side=event.target.classList.contains("left")?"left":event.target.classList.contains("right")?"right":"move";
  const layout=timelineLayout().map.get(clip.id),sourceTrackNode=clipNode.closest("[data-track]");
  const pointerTime=timelineTimeAtPoint(event.clientX,sourceTrackNode);
  selectedClipId=clip.id;selectedAudioClipId="";selectedVoiceoverId="";
  dragState={clip,node:clipNode,startX:event.clientX,startY:event.clientY,original:structuredClone(clip),
    beforeProject:JSON.stringify(project),side,pointerId:event.pointerId,moved:false,changed:false,
    grabOffset:Math.max(0,pointerTime-(layout?.start||0))};
  tracks.setPointerCapture(event.pointerId);if(side==="move")clipNode.classList.add("dragging");
  event.preventDefault();
});
tracks.addEventListener("pointermove",event=>{
  if(!dragState)return;
  const pixelDelta=event.clientX-dragState.startX,delta=pixelDelta/Number($("#timelineZoom").value),{clip,audioClip,original,side}=dragState;
  if(Math.hypot(pixelDelta,event.clientY-dragState.startY)>3)dragState.moved=true;
  if(audioClip){
    if(side!=="move"){
      if(Math.abs(pixelDelta)<1)return;beginTimelineChange();
      if(side==="left"){
        const speed=Math.max(.25,Number(original.speed)||1),low=Math.max(-Number(original.start||0),-Number(original.sourceStart||0)/speed),applied=clamp(delta,low,Number(original.duration)-.05);
        audioClip.start=Number(original.start)+applied;audioClip.sourceStart=Math.max(0,Number(original.sourceStart||0)+applied*speed);audioClip.duration=Math.max(.05,Number(original.duration)-applied);
      }else audioClip.duration=Math.max(.05,Number(original.duration)+delta);
      renderTimeline();return;
    }
    const bounds=timelineScroll.getBoundingClientRect();if(event.clientX<bounds.left+45)timelineScroll.scrollLeft=Math.max(0,timelineScroll.scrollLeft-14);else if(event.clientX>bounds.right-45)timelineScroll.scrollLeft+=14;
    dragState.node.style.transform=`translate(${pixelDelta}px,${event.clientY-dragState.startY}px)`;const target=audioTrackAtPoint(event.clientX,event.clientY);if(target)showTimelineDropUI(event,target);else clearTimelineDropTarget();event.preventDefault();return;
  }
  if(side!=="move"){
    if(Math.abs(pixelDelta)<1)return;beginTimelineChange();
    if(side==="left"&&clip.kind!=="freeze")clip.start=clamp(original.start+delta*original.speed,0,original.end-.05);
    else if(side==="right"&&clip.kind!=="freeze")clip.end=Math.max(original.start+.05,original.end+delta*original.speed);
    else if(side==="right")clip.duration=Math.max(.1,original.duration+delta);
    renderTimeline();loadSelectedPreview(false);return;
  }
  const bounds=timelineScroll.getBoundingClientRect();
  if(event.clientX<bounds.left+45)timelineScroll.scrollLeft=Math.max(0,timelineScroll.scrollLeft-14);
  else if(event.clientX>bounds.right-45)timelineScroll.scrollLeft+=14;
  dragState.node.style.transform=`translate(${pixelDelta}px,${event.clientY-dragState.startY}px)`;
  const target=videoTrackAtPoint(event.clientX,event.clientY);if(target)showTimelineDropUI(event,target);else clearTimelineDropTarget();
  event.preventDefault();
});
function finishTimelineDrag(event,cancelled=false){
  if(!dragState)return;
  const state=dragState,target=!cancelled&&state.side==="move"?(state.audioClip?audioTrackAtPoint(event.clientX,event.clientY):videoTrackAtPoint(event.clientX,event.clientY)):null;
  clearTimelineDropUI();
  if(cancelled){if(state.changed)restoreDraggedClip()}
  else if(state.audioClip&&state.side==="move"&&state.moved&&target){
    const dropTime=timelineTimeAtPoint(event.clientX,target),newStart=Math.round(Math.max(0,dropTime-state.grabOffset)*project.fps)/project.fps;
    if(Math.abs(newStart-Number(state.audioClip.start||0))>.0001){beginTimelineChange();state.audioClip.start=newStart}
  }
  else if(state.side==="move"&&state.moved&&target){
    const targetTrack=Number(target.dataset.track),dropTime=timelineTimeAtPoint(event.clientX,target);
    if(targetTrack===0){
      const targetIndex=primaryDropIndex(state.clip,dropTime),currentIndex=primaryClips().indexOf(state.clip);
      if(targetIndex!==currentIndex||Number(state.clip.track)!==0){beginTimelineChange();moveClipToPrimaryIndex(state.clip,targetIndex)}
    }else{
      const newStart=Math.round(Math.max(0,dropTime-state.grabOffset)*project.fps)/project.fps;
      if(targetTrack!==Number(state.clip.track)||Math.abs(newStart-Number(state.clip.timelineStart||0))>.0001){
        beginTimelineChange();state.clip.track=targetTrack;state.clip.timelineStart=newStart;
      }
    }
  }
  if(tracks.hasPointerCapture(state.pointerId))tracks.releasePointerCapture(state.pointerId);
  const changed=state.changed,moved=state.moved;dragState=null;
  if(changed)snapshot(false);renderAll();
  if(moved){suppressTimelineClick=true;setTimeout(()=>{suppressTimelineClick=false},0)}
  if(changed&&state.side==="move")toast(state.audioClip?"Audio moved on A1":Number(state.clip.track)===0?"Clip reordered on V1":"Clip moved on timeline");
}
tracks.addEventListener("pointerup",event=>finishTimelineDrag(event));
tracks.addEventListener("pointercancel",event=>finishTimelineDrag(event,true));

const dropZone=$("#dropZone");["dragenter","dragover"].forEach(type=>dropZone.addEventListener(type,event=>{event.preventDefault();dropZone.classList.add("drag")}));["dragleave","drop"].forEach(type=>dropZone.addEventListener(type,event=>{event.preventDefault();dropZone.classList.remove("drag")}));dropZone.addEventListener("drop",event=>importFiles(event.dataTransfer.files));
let watermarkDrag=null;$("#imageWatermark").addEventListener("pointerdown",event=>{watermarkDrag={x:event.clientX,y:event.clientY,ox:project.imageWatermark.x,oy:project.imageWatermark.y};event.target.setPointerCapture(event.pointerId)});$("#imageWatermark").addEventListener("pointermove",event=>{if(!watermarkDrag)return;const rect=stage.getBoundingClientRect();project.imageWatermark.x=clamp(watermarkDrag.ox+(event.clientX-watermarkDrag.x)/rect.width,0,1-project.imageWatermark.scale);project.imageWatermark.y=clamp(watermarkDrag.oy+(event.clientY-watermarkDrag.y)/rect.height,0,1-project.imageWatermark.scale);applyPreviewEffects()});$("#imageWatermark").addEventListener("pointerup",()=>{if(watermarkDrag)snapshot(false);watermarkDrag=null;renderInspector()});
document.addEventListener("keydown",event=>{if(["INPUT","SELECT","TEXTAREA"].includes(event.target.tagName))return;const actions={" ":"play",ArrowLeft:"step-back",ArrowRight:"step-forward",Home:"timeline-start",End:"timeline-end","[":"clip-start","]":"clip-end",Delete:"delete",Backspace:"delete"};if(actions[event.key]){event.preventDefault();action(actions[event.key])}if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==="z"){event.preventDefault();action(event.shiftKey?"redo":"undo")}});

async function initialize(){
  const autosave=localStorage.getItem("vdodesk.autosave");if(autosave){try{const saved=JSON.parse(autosave);project={...freshProject(),...(saved.project||{})};media=saved.media||[];}catch{}}
  try{const status=await api("/api/status");$("#version").textContent=`${status.version} · local`;const caps=status.capabilities||{};$("#capabilities").textContent=`Available: ${caps.h264VideoToolbox?"Apple VideoToolbox H.264/HEVC":"software H.264/H.265"}${caps.vp9?", VP9":""}${status.opencv?` · OpenCV ${status.opencv}`:" · manual tracking fallback"}`;}catch(error){toast(error.message)}
  try{await refreshWorkspaceMedia();}catch(error){toast(error.message)}
  await refreshRecent();renderAll();
}
initialize();
