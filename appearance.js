"use strict";

// Presentation-only bridge for the existing appearance system.
// app.js owns the canonical theme/style state and persistence.
document.addEventListener("DOMContentLoaded",()=>{
  document.querySelectorAll("[data-style-choice]").forEach(button=>{
    button.addEventListener("click",()=>{
      if(typeof window.applyStyle==="function") window.applyStyle(button.dataset.styleChoice);
    });
  });
});
