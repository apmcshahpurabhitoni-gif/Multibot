"use strict";

// Read-only presentation bridge for dashboard records that must remain visible
// even when the primary page renderer intentionally stays focused on summaries.
(function(){
  const escapeHtml=value=>String(value??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
  const money=value=>Number.isFinite(Number(value))?`₹${Number(value).toLocaleString("en-IN",{minimumFractionDigits:0,maximumFractionDigits:2})}`:"—";
  const time=value=>{if(!value)return "—";const d=new Date(value);return Number.isNaN(d.getTime())?"—":new Intl.DateTimeFormat("en-IN",{timeZone:"Asia/Kolkata",day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit",hour12:false}).format(d);};
  const load=async()=>{
    const openEl=document.getElementById("historyOpenTrades");
    const scanEl=document.getElementById("historyScanHistory");
    if(!openEl&&!scanEl)return;
    try{
      const response=await fetch(`/api/dashboard?t=${Date.now()}`,{cache:"no-store"});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      const data=await response.json();
      const trades=Array.isArray(data.trades)?data.trades:[];
      const open=trades.filter(t=>String(t.status||"").toUpperCase()==="OPEN");
      const scans=Array.isArray(data.scan_history)?data.scan_history:[];
      if(openEl){
        openEl.innerHTML=open.length?open.map(t=>{
          const side=String(t.type||t.plan?.side||"").toUpperCase();
          const label=t.label||t.symbol||"Unknown asset";
          const strategy=t.strategy||t.plan?.strategy||"Strategy";
          return `<article class="live-trade-row"><div><strong>${escapeHtml(label)}</strong><small>${escapeHtml(strategy)} · ${escapeHtml(side)} · Opened ${escapeHtml(time(t.opened_at||t.signal_ts))}</small></div><div><span>Entry</span><b>${money(t.entry||t.plan?.entry)}</b></div><div><span>Risk</span><b>${money(t.planned_risk||t.plan?.planned_risk)}</b></div><strong class="live-open-badge">OPEN</strong></article>`;
        }).join(""):"<div class=\"empty-state\"><span>◈</span><strong>No open paper trades</strong><small>When a trade is accepted by the runtime it appears here with entry, risk and open timestamp.</small></div>";
      }
      if(scanEl){
        scanEl.innerHTML=scans.length?scans.slice(0,20).map(r=>{const p=r.payload||{};return `<article class="scan-history-row"><div><strong>${escapeHtml(r.strategy_id||"Strategy")}</strong><small>${escapeHtml(time(r.finished_at||r.started_at))}</small></div><span>${escapeHtml(r.status||"—")}</span><small>${Number(p.checked||0)} checked · ${Number(p.directional||0)} directional · ${Number(p.sent||0)} sent · ${Number(p.errors||0)} errors</small></article>`;}).join(""):"<div class=\"empty-state\"><span>◇</span><strong>No scan history yet</strong><small>Completed runtime scans will appear here.</small></div>";
      }
    }catch(error){
      if(openEl)openEl.innerHTML=`<div class="empty-state"><strong>Trade state unavailable</strong><small>${escapeHtml(error.message)}</small></div>`;
      if(scanEl)scanEl.innerHTML=`<div class="empty-state"><strong>Scan history unavailable</strong><small>${escapeHtml(error.message)}</small></div>`;
    }
  };
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",()=>{load();setInterval(load,30000);},{once:true});
  else{load();setInterval(load,30000);}
})();
