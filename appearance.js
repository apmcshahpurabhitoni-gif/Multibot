"use strict";

// Presentation-only bridge. This file owns interface-style state so Neo/Modern
// remains reliable even after dashboard renders or other UI listeners run.
(function initAppearanceBridge(){
  const root=document.documentElement;
  const storage=window.localStorage;
  const THEME_STORAGE_KEY="mavis-theme";
  const STYLE_STORAGE_KEY="mavis-style";
  const ACCENT_STORAGE_KEY="mavis-accent";
  const ACCENTS=["emerald","indigo","amber","rose","cyan"];
  const STYLES=["modern","material3","neo"];
  const validStyle=value=>STYLES.includes(value)?value:"modern";
  const syncStyleClasses=style=>{
    root.classList.toggle("modern-mode",style==="modern");
    root.classList.toggle("material3-mode",style==="material3");
    root.classList.toggle("neo-mode",style==="neo");
  };
  const validAccent=value=>ACCENTS.includes(value)?value:"emerald";

  const sync=(activeAccent)=>{
    const style=validStyle(root.dataset.style||storage.getItem(STYLE_STORAGE_KEY));
    const theme=root.dataset.themePref||root.dataset.theme||storage.getItem(THEME_STORAGE_KEY)||"light";
    root.dataset.style=style;
    syncStyleClasses(style);
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
    document.querySelectorAll("[data-accent-choice]").forEach(button=>{
      const active=button.dataset.accentChoice===activeAccent;
      button.classList.toggle("active",active);
      button.setAttribute("aria-pressed",String(active));
    });
  };

  const applyAccent=accent=>{
    const value=validAccent(accent);
    root.dataset.accent=value;
    storage.setItem(ACCENT_STORAGE_KEY,value);
    sync(value);
  };

  const applyStyle=style=>{
    const value=validStyle(style);
    root.dataset.style=value;
    syncStyleClasses(value);
    storage.setItem(STYLE_STORAGE_KEY,value);
    const currentAccent=root.dataset.accent||storage.getItem(ACCENT_STORAGE_KEY)||"emerald";
    sync(validAccent(currentAccent));
  };

  const bind=()=>{
    const savedStyle=storage.getItem(STYLE_STORAGE_KEY);
    if(savedStyle)root.dataset.style=validStyle(savedStyle);
    const savedAccent=storage.getItem(ACCENT_STORAGE_KEY);
    if(savedAccent)root.dataset.accent=validAccent(savedAccent);

    sync(validAccent(savedAccent||root.dataset.accent||"emerald"));

    // appearance.js is the single owner of style and accent state. The documented
    // contract (THEME_SYSTEM.md §5) requires capture-phase handlers that call
    // preventDefault() and stopImmediatePropagation() so app.js's legacy chip
    // listener can never perform a second, conflicting write (it used to coerce
    // material3 back to modern). Bound guards make re-execution safe.
    if(!root.dataset.appearanceBound){
      root.dataset.appearanceBound="true";
      document.querySelectorAll("[data-style-choice]").forEach(button=>{
        button.addEventListener("click",event=>{
          event.preventDefault();
          event.stopImmediatePropagation();
          applyStyle(button.dataset.styleChoice);
        },true);
      });
    }
    if(!root.dataset.accentBound){
      root.dataset.accentBound="true";
      document.querySelectorAll("[data-accent-choice]").forEach(button=>{
        button.addEventListener("click",event=>{
          event.preventDefault();
          event.stopImmediatePropagation();
          applyAccent(button.dataset.accentChoice);
        },true);
      });
    }
  };

  window.applyStyle=applyStyle;
  window.applyAccent=applyAccent;
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",bind,{once:true});
  else bind();
})();
