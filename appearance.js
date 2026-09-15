"use strict";

document.addEventListener("DOMContentLoaded",()=>{
  const root=document.documentElement;
  const storage=window.localStorage;
  const sync=()=>{
    document.querySelectorAll("[data-theme-choice]").forEach(button=>{const active=button.dataset.themeChoice===root.dataset.theme;button.classList.toggle("active",active);button.setAttribute("aria-pressed",String(active));});
    document.querySelectorAll("[data-style-choice]").forEach(button=>{const active=button.dataset.styleChoice===root.dataset.style;button.classList.toggle("active",active);button.setAttribute("aria-pressed",String(active));});
    document.querySelectorAll("[data-setting-state]").forEach(button=>{const active=storage.getItem(`mavis-${button.dataset.settingState}`)==="true";button.classList.toggle("active",active);button.setAttribute("aria-pressed",String(active));});
  };
  const setTheme=theme=>{root.dataset.theme=theme==="dark"?"dark":"light";storage.setItem("mavis-theme",root.dataset.theme);sync();};
  const setStyle=style=>{root.dataset.style=style==="neo"?"neo":"modern";storage.setItem("mavis-style",root.dataset.style);sync();};
  const savedTheme=storage.getItem("mavis-theme");const savedStyle=storage.getItem("mavis-style");
  if(savedTheme)root.dataset.theme=savedTheme==="dark"?"dark":"light";
  if(savedStyle)root.dataset.style=savedStyle==="neo"?"neo":"modern";
  document.querySelectorAll("[data-theme-choice]").forEach(button=>button.addEventListener("click",()=>setTheme(button.dataset.themeChoice)));
  document.querySelectorAll("[data-style-choice]").forEach(button=>button.addEventListener("click",()=>setStyle(button.dataset.styleChoice)));
  document.getElementById("themeToggle")?.addEventListener("click",()=>setTheme(root.dataset.theme==="dark"?"light":"dark"));
  [["compactModeToggle","compact"],["reduceMotionToggle","reduce-motion"]].forEach(([id,key])=>{const button=document.getElementById(id);if(!button)return;button.dataset.settingState=key;button.addEventListener("click",()=>{const next=storage.getItem(`mavis-${key}`)!=="true";storage.setItem(`mavis-${key}`,String(next));root.dataset[key]=next?"on":"off";sync();});});
  window.applyStyle=setStyle;
  sync();
});