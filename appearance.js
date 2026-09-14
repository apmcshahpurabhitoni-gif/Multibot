"use strict";

// Appearance controls deliberately stay independent from page/runtime logic.
// app.js remains the owner of initial state; this binds the style controls
// directly so they cannot fail because of a non-global function dependency.
document.addEventListener("DOMContentLoaded",()=>{
  const root=document.documentElement;
  const sync=()=>{
    document.querySelectorAll("[data-style-choice]").forEach(button=>{
      button.classList.toggle("active",button.dataset.styleChoice===root.dataset.style);
    });
  };
  document.querySelectorAll("[data-style-choice]").forEach(button=>{
    button.addEventListener("click",()=>{
      const style=button.dataset.styleChoice==="neo"?"neo":"modern";
      root.dataset.style=style;
      localStorage.setItem("mavis-style",style);
      sync();
    });
  });
  sync();
});