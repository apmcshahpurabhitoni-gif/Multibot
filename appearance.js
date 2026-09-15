"use strict";

// Presentation-only bridge. app.js owns the existing header/theme/settings
// controls; this file owns interface-style buttons and keeps the visual state
// synchronized without registering duplicate click handlers.
(function initAppearanceBridge(){
  const root=document.documentElement;
  const storage=window.localStorage;
  const validStyle=value=>value==="neo"?"neo":"modern";

  const sync=()=>{
    document.querySelectorAll("[data-style-choice]").forEach(button=>{
      const active=button.dataset.styleChoice===root.dataset.style;
      button.classList.toggle("active",active);
      button.setAttribute("aria-pressed",String(active));
    });
    document.querySelectorAll("[data-theme-choice]").forEach(button=>{
      const active=button.dataset.themeChoice===root.dataset.theme;
      button.classList.toggle("active",active);
      button.setAttribute("aria-pressed",String(active));
    });
  };

  const applyStyle=style=>{
    const value=validStyle(style);
    root.dataset.style=value;
    storage.setItem("mavis-style",value);
    sync();
  };

  const bind=()=>{
    const savedStyle=storage.getItem("mavis-style");
    if(savedStyle)root.dataset.style=validStyle(savedStyle);

    document.querySelectorAll("[data-style-choice]").forEach(button=>{
      if(button.dataset.appearanceBound==="true")return;
      button.dataset.appearanceBound="true";
      button.addEventListener("click",()=>applyStyle(button.dataset.styleChoice));
    });

    // Theme choice state is synchronized here; click ownership stays with the
    // main runtime controller so a single user action cannot be applied twice.
    sync();
  };

  window.applyStyle=applyStyle;
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",bind,{once:true});
  else bind();
})();
