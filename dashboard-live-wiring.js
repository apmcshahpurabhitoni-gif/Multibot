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
  const dateKey=value=>{if(!value)return "unknown";const d=new Date(value);if(Number.isNaN(d.getTime()))return "unknown";return new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Kolkata",year:"numeric",month:"2-digit",day:"2-digit"}).format(d);};
  const dateLabel=key=>{if(key==="unknown")return "Unknown date";const d=new Date(`${key}T00:00:00`);return Number.isNaN(d.getTime())?"Unknown date":new Intl.DateTimeFormat("en-IN",{timeZone:"Asia/Kolkata",weekday:"short",day:"2-digit",month:"short",year:"numeric"}).format(d);};
  const openGroups=new Set(),scanGroups=new Set(),groupInit=new Set();
  let lastSnapshot=null;
  const groupToggle=(kind,key,open,label,sub)=>`<button class="history-date-toggle" type="button" data-history-date="${escapeHtml(key)}" data-history-kind="${kind}" aria-expanded="${open}"><span><b>${escapeHtml(label)}</b><small>${escapeHtml(sub)}</small></span><i aria-hidden="true" class="collapse-control">⌄</i></button>`;
  const dateGroups=(rows,kind,groups,rowRenderer,dateOf,noun)=>{
    const byDate=new Map();
    rows.forEach(row=>{const key=dateKey(dateOf(row));if(!byDate.has(key))byDate.set(key,[]);byDate.get(key).push(row);});
    const ordered=[...byDate.entries()].sort((a,b)=>b[0].localeCompare(a[0]));
    if(!groupInit.has(kind)){groupInit.add(kind);if(!groups.size&&ordered[0])groups.add(`${kind}:${ordered[0][0]}`);}
    return ordered.map(([date,items])=>{
      const key=`${kind}:${date}`,open=groups.has(key);
      return `<section class="history-date-group ${open?"is-open":""}">${groupToggle(kind,key,open,dateLabel(date),`${items.length} ${noun}${items.length===1?"":"s"}`)}${open?`<div class="history-date-rows">${items.map(rowRenderer).join("")}</div>`:""}</section>`;
    }).join("");
  };
  const render=data=>{
    lastSnapshot=data;
    const openEl=document.getElementById("historyOpenTrades");
    const scanEl=document.getElementById("historyScanHistory");
    if(!openEl&&!scanEl)return;
    const trades=Array.isArray(data?.trades)?data.trades:[];
    const open=trades.filter(t=>String(t.status||"").toUpperCase()==="OPEN");
    const scans=Array.isArray(data?.scan_history)?data.scan_history:[];
    if(openEl){
      openEl.innerHTML=open.length?dateGroups(open,"open",openGroups,t=>{
        const side=String(t.type||t.plan?.side||"").toUpperCase();
        const label=t.label||t.symbol||"Unknown asset";
        const strategy=t.strategy||t.plan?.strategy||"Strategy";
        const livePnl=t.pnl??t.live_pnl??t.unrealized_pnl;
        return `<article class="live-trade-row"><div><strong>${escapeHtml(label)}</strong><small>${escapeHtml(strategy)} · ${escapeHtml(side)} · Opened ${escapeHtml(time(t.opened_at||t.signal_ts))}</small></div><div><span>Entry</span><b>${money(t.entry||t.plan?.entry)}</b></div><div><span>Risk</span><b>${money(t.planned_risk||t.plan?.planned_risk)}</b></div><div><span>Live P/L</span><b class="${pnlClass(livePnl)}">${pnl(livePnl)}</b></div><strong class="live-open-badge">OPEN</strong></article>`;
      },t=>t.opened_at||t.signal_ts,"open trade"):"<div class=\"empty-state\"><span>◈</span><strong>No open paper trades</strong><small>When a trade is accepted by the runtime it appears here with entry, risk and open timestamp.</small></div>";
    }
    if(scanEl){
      scanEl.innerHTML=scans.length?dateGroups(scans.slice(0,60),"scan",scanGroups,r=>{
        const p=r.payload||{};
        return `<article class="scan-history-row"><div><strong>${escapeHtml(r.strategy_id||"Strategy")}</strong><small>${escapeHtml(time(r.finished_at||r.started_at))}</small></div><span>${escapeHtml(r.status||"—")}</span><small>${Number(p.checked||0)} checked · ${Number(p.directional||0)} directional · ${Number(p.sent||0)} sent · ${Number(p.errors||0)} errors</small></article>`;
      },r=>r.finished_at||r.started_at,"scan"):"<div class=\"empty-state\"><span>◇</span><strong>No scan history yet</strong><small>Completed runtime scans will appear here.</small></div>";
    }
  };
  document.addEventListener("click",event=>{
    const toggle=event.target.closest("[data-history-date]");
    if(!toggle)return;
    const kind=toggle.dataset.historyKind;
    if(kind!=="open"&&kind!=="scan")return;
    const groups=kind==="open"?openGroups:scanGroups;
    const key=toggle.dataset.historyDate;
    if(groups.has(key))groups.delete(key);else groups.add(key);
    if(lastSnapshot)render(lastSnapshot);
  });

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
