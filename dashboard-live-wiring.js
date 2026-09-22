"use strict";

// Read-only presentation bridge for dashboard records that must remain visible.
// app.js owns the single /api/dashboard request lifecycle; this bridge only
// renders Open Positions and Scan History from those already-fetched snapshots.
(function(){
  const escapeHtml=value=>String(value??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
  const money=value=>Number.isFinite(Number(value))?`₹${Number(value).toLocaleString("en-IN",{minimumFractionDigits:0,maximumFractionDigits:2})}`:"—";
  const pnl=value=>{const n=Number(value);if(!Number.isFinite(n))return "—";return `${n>=0?"+":"−"}${money(Math.abs(n))}`;};
  const pnlClass=value=>{const n=Number(value);return Number.isFinite(n)?n>0?"positive":n<0?"negative":"":"";};
  const time=value=>{if(!value)return "—";const d=new Date(value);return Number.isNaN(d.getTime())?"—":new Intl.DateTimeFormat("en-IN",{timeZone:"Asia/Kolkata",day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit",hour12:false}).format(d);};
  const render=data=>{
    const openEl=document.getElementById("historyOpenTrades");
    const scanEl=document.getElementById("historyScanHistory");
    if(!openEl&&!scanEl)return;
    const trades=Array.isArray(data?.trades)?data.trades:[];
    const open=trades.filter(t=>String(t.status||"").toUpperCase()==="OPEN");
    const scans=Array.isArray(data?.scan_history)?data.scan_history:[];
    if(openEl){
      openEl.innerHTML=open.length?open.map(t=>{
        const side=String(t.type||t.plan?.side||"").toUpperCase();
        const label=t.label||t.symbol||"Unknown asset";
        const strategy=t.strategy||t.plan?.strategy||"Strategy";
        return `<article class="live-trade-row"><div><strong>${escapeHtml(label)}</strong><small>${escapeHtml(strategy)} · ${escapeHtml(side)} · Opened ${escapeHtml(time(t.opened_at||t.signal_ts))}</small></div><div><span>Entry</span><b>${money(t.entry||t.plan?.entry)}</b></div><div><span>Risk</span><b>${money(t.planned_risk||t.plan?.planned_risk)}</b></div><strong class="live-open-badge">OPEN</strong></article>`;
      }).join(""):"<div class=\"empty-state\"><span>◈</span><strong>No open paper trades</strong><small>When a trade is accepted by the runtime it appears here with entry, risk and open timestamp.</small></div>";
    }
    if(scanEl){
      if(!scans.length){
        scanEl.innerHTML="<div class=\"empty-state\"><span>◇</span><strong>No scan history yet</strong><small>Completed runtime scans will appear here.</small></div>";
      }else{
        const groups=new Map();
        scans.slice(0,50).forEach(r=>{
          const raw=r.finished_at||r.completed_at||r.started_at||r.created_at||r.timestamp||r.run_at||r.updated_at;
          const d=raw?new Date(raw):null;
          const key=d&&!Number.isNaN(d.getTime())?new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Kolkata",year:"numeric",month:"2-digit",day:"2-digit"}).format(d):"unknown";
          if(!groups.has(key))groups.set(key,[]);
          groups.get(key).push(r);
        });
        const label=key=>{if(key==="unknown")return "Unknown date";const d=new Date(key+"T00:00:00");return Number.isNaN(d.getTime())?"Unknown date":new Intl.DateTimeFormat("en-IN",{timeZone:"Asia/Kolkata",weekday:"short",day:"2-digit",month:"short",year:"numeric"}).format(d);};
        scanEl.innerHTML=[...groups.entries()].sort((a,b)=>b[0].localeCompare(a[0])).map(([date,rows])=>`<section class="history-date-group is-open"><button class="history-date-toggle" type="button" data-history-date="history-scan-date:${escapeHtml(date)}" data-history-kind="scan" aria-expanded="true"><span><b>${escapeHtml(label(date))}</b><small>${rows.length} scan${rows.length===1?"":"s"}</small></span><i>⌃</i></button><div class="history-date-rows">${rows.map(r=>{const p=r.payload||{};return `<article class="history-scan-row scan-history-row"><div class="history-scan-identity"><strong>${escapeHtml(r.strategy_id||r.strategy||"Strategy")}</strong><small>${escapeHtml(time(r.finished_at||r.completed_at||r.started_at||r.created_at||r.timestamp||r.run_at||r.updated_at))}</small></div><span class="history-scan-status">${escapeHtml(r.status||"—")}</span><div class="history-scan-metrics"><span>${Number(p.checked||0)} checked</span><span>${Number(p.directional||0)} directional</span><span>${Number(p.sent||0)} sent</span><span>${Number(p.errors||0)} errors</span></div></article>`;}).join("")}</div></section>`).join("");
      }
    }
  };

  // Observe the canonical dashboard fetch instead of starting a second poller.
  const nativeFetch=window.fetch.bind(window);
  window.fetch=async(...args)=>{
    const response=await nativeFetch(...args);
    try{
      const requestUrl=typeof args[0]==="string"?args[0]:args[0]?.url||"";
      const url=new URL(requestUrl,window.location.href);
      if(url.pathname==="/api/dashboard"){
        const payload=await response.clone().json();
        render(payload);
      }
    }catch(error){
      // The primary app loader owns API errors; this presentation bridge must
      // never turn a dashboard fetch into a failed runtime request.
    }
    return response;
  };
})();
