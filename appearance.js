"use strict";

// Presentation-only bridge. This file owns interface-style state so Neo/Modern
// remains reliable even after dashboard renders or other UI listeners run.
(function initAppearanceBridge(){
  const root=document.documentElement;
  const storage=window.localStorage;
  const THEME_STORAGE_KEY="mavis-theme";
  const STYLE_STORAGE_KEY="mavis-style";
  const validStyle=value=>value==="neo"?"neo":"modern";

  const sync=()=>{
    const style=validStyle(root.dataset.style||storage.getItem(STYLE_STORAGE_KEY));
    const theme=root.dataset.themeChoice||root.dataset.theme||storage.getItem(THEME_STORAGE_KEY)||"light";
    root.dataset.style=style;
    root.classList.toggle("neo-mode",style==="neo");
    root.classList.toggle("modern-mode",style!=="neo");
    document.querySelectorAll("[data-style-choice]").forEach(button=>{
      const active=button.dataset.styleChoice===style;
      button.classList.toggle("active",active);
      button.setAttribute("aria-pressed",String(active));
    });
    document.querySelectorAll("[data-theme-choice]").forEach(button=>{
      const active=button.dataset.themeChoice===theme;
      button.classList.toggle("active",active);
      button.setAttribute("aria-pressed",String(active));
    });
  };

  const applyStyle=style=>{
    const value=validStyle(style);
    root.dataset.style=value;
    root.classList.toggle("neo-mode",value==="neo");
    root.classList.toggle("modern-mode",value!=="neo");
    storage.setItem(STYLE_STORAGE_KEY,value);
    sync();
  };

  const bind=()=>{
    const savedStyle=storage.getItem(STYLE_STORAGE_KEY);
    if(savedStyle)root.dataset.style=validStyle(savedStyle);

    if(!root.dataset.appearanceBound){
      root.dataset.appearanceBound="true";
      document.addEventListener("click",event=>{
        const button=event.target.closest("[data-style-choice]");
        if(!button)return;
        event.preventDefault();
        applyStyle(button.dataset.styleChoice);
      });
    }

    sync();
  };

  window.applyStyle=applyStyle;
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",bind,{once:true});
  else bind();
})();
