"use strict";

// Presentation-only controller. Runtime, trading, backtest and API state stay
// owned by app.js and the server.
document.addEventListener("DOMContentLoaded",()=>{
  const root=document.documentElement;
  const storage=window.localStorage;
  const validTheme=value=>value==="dark"?"dark":"light";
  const validStyle=value=>value==="neo"?"neo":"modern";
  const applyTheme=theme=>{root.dataset.theme=validTheme(theme);storage.setItem("mavis-theme",root.dataset.theme);sync();};
  const applyStyle=style=>{root.dataset.style=validStyle(style);storage.setItem("mavis-style",root.dataset.style);sync();};
  const sync=()=>{
    document.querySelectorAll("[data-theme-choice]").forEach(button=>{
      const active=button.dataset.themeChoice===root.dataset.theme;
      button.classList.toggle("active",active);
      button.setAttribute("aria-pressed",String(active));
    });
    document.querySelectorAll("[data-style-choice]").forEach(button=>{
      const active=button.dataset.styleChoice===root.dataset.style;
      button.classList.toggle("active",active);
      button.setAttribute("aria-pressed",String(active));
    });
    document.querySelectorAll("[data-setting-state]").forEach(button=>{
      const active=storage.getItem(`mavis-${button.dataset.settingState}`)==="true";
      button.classList.toggle("active",active);
      button.setAttribute("aria-pressed",String(active));
    });
  };

  const savedTheme=storage.getItem("mavis-theme");
  const savedStyle=storage.getItem("mavis-style");
  if(savedTheme)root.dataset.theme=validTheme(savedTheme);
  if(savedStyle)root.dataset.style=validStyle(savedStyle);

  document.querySelectorAll("[data-theme-choice]").forEach(button=>button.addEventListener("click",()=>applyTheme(button.dataset.themeChoice)));
  document.querySelectorAll("[data-style-choice]").forEach(button=>button.addEventListener("click",()=>applyStyle(button.dataset.styleChoice)));

  const themeToggle=document.getElementById("themeToggle");
  themeToggle?.addEventListener("click",()=>applyTheme(root.dataset.theme==="dark"?"light":"dark"));

  [["compactModeToggle","compact"],["reduceMotionToggle","reduce-motion"]].forEach(([id,key])=>{
    const button=document.getElementById(id);
    if(!button)return;
    button.dataset.settingState=key;
    button.addEventListener("click",()=>{
      const next=storage.getItem(`mavis-${key}`)!=="true";
      storage.setItem(`mavis-${key}`,String(next));
      root.dataset[key]=next?"on":"off";
      sync();
    });
  });

  // Compatibility hook for the existing appearance bridge/tests. It remains
  // presentation-only and never changes application/runtime state.
  window.applyStyle=applyStyle;
  sync();
});