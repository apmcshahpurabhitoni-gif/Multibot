"use strict";
const CONFIG=Object.freeze({apiUrl:window.DASHBOARD_API_URL||"/api/dashboard",timezone:"Asia/Kolkata",refreshMs:30000});
// Signals and trades recorded before the "Rename strategy display names"
// commits (bcb47ba sweep_v2, 62d81b6 engulfing_66_sma, 1eedaff adaptive_trend)
// stored the old display name. Every rename kept the strategy id and the
// version, so these are the same strategies under a former name -- mapping to
// the ID and letting the registry supply the name keeps the stored history
// intact and survives a future rename without another edit here.
const LEGACY_STRATEGY_NAMES=Object.freeze({"Sweep V2":"sweep_v2","Engulfing Entries @ 66 SMA":"engulfing_66_sma","Adaptive Trend Momentum":"adaptive_trend"});
const state={data:null,lastUpdate:null,activePage:"overview",expanded:new Set(),signalDates:new Set(),historyTradeDates:new Set(),historyScanDates:new Set(),groupInit:new Set(),selectedTrade:null,calendarDate:dateInputValue(new Date()),calendarImpacts:new Set(["All"]),calendarDates:new Set(),calendar:null,backtest:null,settings:null,settingsDirty:false,settingsMessage:null};
const $=id=>document.getElementById(id);const $$=selector=>Array.from(document.querySelectorAll(selector));
function escapeHtml(value){return String(value??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");}
function number(value,digits=2){const n=Number(value);return Number.isFinite(n)?n.toLocaleString("en-IN",{minimumFractionDigits:digits,maximumFractionDigits:digits}):"—";}
function inr(value){const n=Number(value);return Number.isFinite(n)?`₹${n.toLocaleString("en-IN",{minimumFractionDigits:0,maximumFractionDigits:2})}`:"—";}
function price(value){return number(value,2);}
function timestamp(value){if(!value)return "—";const d=new Date(value);if(Number.isNaN(d.getTime()))return "—";return new Intl.DateTimeFormat("en-IN",{timeZone:CONFIG.timezone,day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",hour12:false}).format(d);}
function dateLabel(value){if(!value)return "Unknown date";const d=new Date(`${value}T00:00:00`);if(Number.isNaN(d.getTime()))return "Unknown date";return new Intl.DateTimeFormat("en-IN",{timeZone:CONFIG.timezone,weekday:"short",day:"2-digit",month:"short",year:"numeric"}).format(d);}
function dateInputValue(value){const d=value instanceof Date?value:new Date(value);const p=new Intl.DateTimeFormat("en-CA",{timeZone:CONFIG.timezone,year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(d);const m=Object.fromEntries(p.map(x=>[x.type,x.value]));return `${m.year}-${m.month}-${m.day}`;}
function dateKey(value){if(!value)return "unknown";const d=new Date(value);if(Number.isNaN(d.getTime()))return "unknown";return dateInputValue(d);}
function clock(){return new Intl.DateTimeFormat("en-IN",{timeZone:CONFIG.timezone,hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false}).format(new Date());}
function safeApiError(status,text){const compact=String(text||"").replace(/\s+/g," ").trim();return compact?`HTTP ${status}: ${compact.slice(0,240)}`:`HTTP ${status}`;}
async function readJsonResponse(response,context="Request"){const text=await response.text();let payload=null;if(text.trim()){try{payload=JSON.parse(text);}catch(error){const type=response.headers.get("content-type")||"unknown content type";throw new Error(`${context} returned invalid JSON (${type}). ${safeApiError(response.status,text)}`);}}if(!response.ok)throw new Error(payload?.error||safeApiError(response.status,text)||`${context} failed`);if(!payload||typeof payload!=="object")throw new Error(`${context} returned an empty response.`);return payload;}
function direction(signal){const s=String(signal||"NO_SIGNAL").toUpperCase();if(s==="BUY")return{text:"BUY",icon:"🟢",cls:"buy"};if(s==="SELL")return{text:"SELL",icon:"🔴",cls:"sell"};if(s==="NEUTRAL")return{text:"NEUTRAL",icon:"⚪",cls:"neutral"};return{text:"NO SIGNAL",icon:"·",cls:"neutral"};}function assetInfo(symbol){const rows=state.data?.universe?.asset_metadata||[];return rows.find(row=>row.symbol===symbol||row.ticker===symbol)||null;}
function assetLabel(symbol,fallback){const info=assetInfo(symbol);return info?.label||fallback||symbol||"Unknown asset";}
function strategyInfo(value){const rows=state.data?.strategies||[],key=LEGACY_STRATEGY_NAMES[value]||value;return rows.find(row=>row.id===key||row.name===key)||null;}
function strategyLabel(value){return strategyInfo(value)?.name||value||"Strategy";}
function canonicalSignals(){const rows=Array.isArray(state.data?.signals)?state.data.signals:[];const latest=new Map();rows.filter(row=>["BUY","SELL"].includes(String(row.signal||row.direction||"").toUpperCase())).forEach(row=>{const key=row.signal_key||[row.strategy,row.symbol,row.signal||row.direction,row.timestamp].join("|");const previous=latest.get(key);if(!previous||String(row.updated_at||row.created_at||row.timestamp)>String(previous.updated_at||previous.created_at||previous.timestamp))latest.set(key,row);});return [...latest.values()].sort((a,b)=>String(b.timestamp).localeCompare(String(a.timestamp)));}
function activeSignals(){return canonicalSignals().filter(signal=>freshness(signal).label==="FRESH");}
function supportedBacktestAssets(strategyId){const strategy=strategyInfo(strategyId);const allowed=new Set(strategy?.assets||[]);return (state.data?.backtest_assets||[]).filter(asset=>!allowed.size||allowed.has(asset.key||asset.ticker));}
function freshness(signal){const status=String(signal?.freshness||"UNKNOWN").toUpperCase();return status==="FRESH"?{label:"FRESH",cls:"fresh"}:status==="STALE"?{label:"STALE",cls:"stale"}:{label:status||"UNKNOWN",cls:"stale"};}
function ageText(signal){const minutes=Number(signal?.age_minutes);if(!Number.isFinite(minutes)||minutes<0)return "Unavailable";return minutes<60?`${Math.floor(minutes)} min ago`:`${Math.floor(minutes/60)} hr ${Math.floor(minutes%60)} min ago`;}
function keyFor(prefix,item,index){const raw=item?.id||item?.signal_key||item?.timestamp||item?.closed_at||`${index}`;return `${prefix}:${raw}:${item?.symbol||item?.strategy||item?.plan?.strategy||"item"}`;}
function expandButton(key,label){const open=state.expanded.has(key);const card=open?"expanded":"";return `<button class="expand-button collapse-control ${open?"is-open":""}" type="button" data-expand="${escapeHtml(key)}" aria-expanded="${open}" aria-label="${open?"Collapse":"Expand"} ${escapeHtml(label)}" tabindex="-1" aria-hidden="true"></button>`;}
function signalCard(signal,index){const key=keyFor("signal",signal,index),d=direction(signal.signal),age=freshness(signal),symbol=signal.symbol||signal.asset||"Unknown asset",label=assetLabel(symbol,signal.label),strategy=strategyLabel(signal.strategy),open=state.expanded.has(key),timeframe=signal.timeframe||strategyInfo(signal.strategy)?.timeframes?.[0]||"—";const details=open?`<div class="expand-content"><div class="detail-grid"><div><span>Strategy</span><b>${escapeHtml(strategy)}</b></div><div><span>Direction</span><b>${d.icon} ${d.text}</b></div><div><span>Timeframe</span><b>${escapeHtml(timeframe)}</b></div><div><span>Actionable</span><b>${signal.actionable===true?"YES":"NO"}</b></div><div><span>Freshness</span><b class="${age.cls}">${age.label}</b></div><div><span>Candle closed</span><b>${escapeHtml(timestamp(signal.timestamp))}</b></div><div><span>Age</span><b>${escapeHtml(ageText(signal))}</b></div><div><span>Pipeline</span><b>${escapeHtml(signal.pipeline_status||"—")}</b></div><div><span>Telegram</span><b>${escapeHtml(signal.delivery?.status||"NOT_SENT")}</b></div><div><span>Send count</span><b>${number(signal.send_count||signal.send_state?.send_count,0)} / 2</b></div><div><span>First sent</span><b>${escapeHtml(timestamp(signal.first_sent_at||signal.send_state?.first_sent_at))}</b></div></div><div class="reason"><span>Strategy reason</span><p>${escapeHtml(signal.reason||"No reason supplied by runtime.")}</p></div></div>`:"";const hasLevels=signal.has_trade_levels===true&&[signal.entry,signal.take_profit,signal.stop_loss].every(value=>Number.isFinite(Number(value))&&Number(value)>0)||[signal.entry,signal.take_profit,signal.stop_loss].every(value=>Number.isFinite(Number(value))&&Number(value)>0);const lifecycle=String(signal.pipeline_status||signal.delivery?.status||"RECORDED").replaceAll("_"," ");const freshnessLabel=String(age.label||"RECORDED");const status=lifecycle.toUpperCase()===freshnessLabel.toUpperCase()?lifecycle:`${lifecycle} · ${freshnessLabel}`;// The collapsed row must name the strategy that produced the signal, without
// the reader having to expand every card to find out. renderOpenHistoryRow
// already leads its sub-line with the strategy, so this matches it. The
// direction stays on the card twice over (the .direction-icon and the
// .signal-side badge), so the summary trades that duplicate for the strategy
// and keeps the same segment count under the 2-line -webkit-line-clamp.
const summary=hasLevels?`${strategy} · Entry ${price(signal.entry)} · Target ${price(signal.take_profit)} · Stop ${price(signal.stop_loss)}`:`${strategy} · ${status}`;return `<article class="signal-card ${d.cls} ${open?"expanded":""} ${hasLevels?"has-levels":"incomplete"}"><div class="card-main" data-expand="${escapeHtml(key)}" role="button" tabindex="0" aria-expanded="${open}" aria-label="${open?"Collapse":"Expand"} details for ${escapeHtml(label)} from ${escapeHtml(strategy)}"><div class="signal-leading"><span class="direction-icon">${d.icon}</span><div><strong>${escapeHtml(label)}</strong><small>${escapeHtml(summary)}</small></div></div><div class="card-state"><span class="signal-side ${d.cls}">${d.text}</span>${expandButton(key,symbol)}</div></div>${details}</article>`;}
function empty(message,icon="·",detail="There is nothing to display in the current snapshot."){return `<div class="empty-state"><span>${icon}</span><strong>${escapeHtml(message)}</strong><small>${escapeHtml(detail)}</small></div>`;}
function renderSignalChart(){const signals=canonicalSignals(),days=[],today=new Date();for(let i=13;i>=0;i--){const d=new Date(today);d.setDate(d.getDate()-i);days.push({key:dateKey(d),label:new Intl.DateTimeFormat("en-IN",{timeZone:CONFIG.timezone,day:"2-digit",month:"short"}).format(d),count:0});}const map=new Map(days.map(d=>[d.key,d]));signals.forEach(s=>{const row=map.get(dateKey(s.timestamp));if(row)row.count++;});const total=days.reduce((sum,d)=>sum+d.count,0);if(!total){$("signalActivityChart").innerHTML=empty("No signal activity in the last 14 days","◇","Signals outside this 14-day window are retained in Signals and History.");return;}const max=Math.max(1,...days.map(d=>d.count)),width=720,height=180,left=28,right=10,top=14,bottom=32,plotW=width-left-right,plotH=height-top-bottom,barW=Math.max(12,plotW/days.length*.55);const bars=days.map((d,i)=>{const x=left+i*plotW/days.length+(plotW/days.length-barW)/2,h=d.count/max*plotH,y=top+plotH-h;return `<rect class="chart-bar" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(2,h).toFixed(1)}" rx="4"><title>${escapeHtml(d.label)} · ${d.count} signal${d.count===1?"":"s"}</title></rect><text class="chart-label" x="${(x+barW/2).toFixed(1)}" y="${height-14}" text-anchor="middle">${escapeHtml(d.label)}</text>`;}).join("");$("signalActivityChart").innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Signal activity for the last 14 days"><line class="chart-axis" x1="${left}" y1="${top+plotH}" x2="${width-right}" y2="${top+plotH}"/><text class="chart-y" x="8" y="${top+plotH+4}">0</text>${bars}</svg>`;}
function renderEquityLine(points,{width=720,height=230,label="Equity curve"}={}){const safe=points.filter(p=>Number.isFinite(Number(p.equity)));if(!safe.length)return "";const values=safe.map(p=>Number(p.equity)),min=Math.min(...values),max=Math.max(...values),pad=Math.max(1,(max-min)*.12);const lo=min-pad,hi=max+pad||1,mobile=window.matchMedia("(max-width:560px)").matches,chartHeight=mobile?180:height,left=mobile?14:18,right=10,top=mobile?10:16,bottom=mobile?24:32,plotW=width-left-right,plotH=chartHeight-top-bottom;const xy=safe.map((p,i)=>{const x=left+(safe.length===1?plotW/2:i*plotW/(safe.length-1));const y=top+plotH-(Number(p.equity)-lo)/(hi-lo)*plotH;return [x,y];});const line=xy.map((p,i)=>`${i?"L":"M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");const area=`${line} L${xy[xy.length-1][0].toFixed(1)} ${(top+plotH).toFixed(1)} L${xy[0][0].toFixed(1)} ${(top+plotH).toFixed(1)} Z`;const start=safe[0],end=safe[safe.length-1];return `<svg viewBox="0 0 ${width} ${chartHeight}" role="img" aria-label="${escapeHtml(label)}"><line class="chart-grid" x1="${left}" y1="${top+plotH/2}" x2="${width-right}" y2="${top+plotH/2}"/><line class="chart-axis" x1="${left}" y1="${top+plotH}" x2="${width-right}" y2="${top+plotH}"/><path class="equity-area" d="${area}"/><path class="equity-line" d="${line}"/><circle class="equity-point" cx="${xy[0][0].toFixed(1)}" cy="${xy[0][1].toFixed(1)}" r="3"><title>Start · ${inr(start.equity)}</title></circle><circle class="equity-point" cx="${xy[xy.length-1][0].toFixed(1)}" cy="${xy[xy.length-1][1].toFixed(1)}" r="3"><title>Current · ${inr(end.equity)}</title></circle><text class="chart-y" x="${left}" y="12">${escapeHtml(inr(hi))}</text><text class="chart-y" x="${left}" y="${chartHeight-8}">${escapeHtml(inr(lo))}</text></svg>`;}
function renderOverview(){const data=state.data||{},signals=canonicalSignals(),active=activeSignals(),trades=Array.isArray(data.trades)?data.trades:[],open=trades.filter(t=>String(t.status||"").toUpperCase()==="OPEN"),closed=trades.filter(t=>String(t.status||"").toUpperCase()==="CLOSED"),accounts=Array.isArray(data.accounts?.data)?data.accounts.data:[],system=data.system||{},online=String(system.status||"").toUpperCase()==="ONLINE";const starting=accounts.reduce((sum,a)=>sum+Number(a.starting_balance||0),0)||100000;const current=accounts.reduce((sum,a)=>sum+Number(a.balance||0),0)||starting;const pnl=closed.reduce((sum,t)=>sum+Number(t.pnl||0),0);const points=[{timestamp:data.generated_at||state.lastUpdate,equity:starting}];closed.slice().sort((a,b)=>String(tradeDateValue(a)).localeCompare(String(tradeDateValue(b)))).forEach(t=>points.push({timestamp:tradeDateValue(t),equity:points[points.length-1].equity+Number(t.pnl||0)}));if(points.length===1||Math.abs(points[points.length-1].equity-current)>0.01)points.push({timestamp:data.generated_at||state.lastUpdate,equity:current});$("overviewAccountValue").textContent=inr(current);$("overviewTotalPnl").textContent=inr(pnl);$("overviewTradeCount").textContent=open.length;$("overviewSignalCount").textContent=active.length;$("equityCurveValue").textContent=inr(current);$("equityCurveRange").textContent=`${closed.length} completed trade${closed.length===1?"":"s"}`;$("equityCurveChart").innerHTML=renderEquityLine(points,{label:"Total paper account equity over completed trades"});renderSignalChart();const signalPill=$("heroSignalPill"),assetPill=$("heroAssetPill"),updatePill=$("heroUpdatePill");if(signalPill)signalPill.textContent=`${active.length} ACTIVE SIGNAL${active.length===1?"":"S"}`;if(assetPill)assetPill.textContent=`${Number(data.universe?.count||0)} ASSETS WATCHING`;if(updatePill)updatePill.textContent=online?"● SYSTEM ONLINE":"● SYSTEM WAITING";$("versionBadge").textContent=`v${escapeHtml(data.version||"2.0.0")}`;$("overviewSignals").innerHTML=active.length?active.slice(0,5).map(signalCard).join(""):empty("No signal records","◇",String(data.scan?.status).toUpperCase()==="COMPLETE"?"The latest completed scan found no approved directional signal.":"No completed scan has been recorded yet.");}
function tradeDateValue(trade){return trade.closed_at||trade.exit_timestamp||trade.opened_at||trade.created_at||trade.timestamp||trade.signal_ts||trade.plan?.signal_timestamp;}
function renderTradeRow(trade,index){const plan=trade.plan||trade,side=String(plan.side||trade.type||"").toUpperCase(),d=direction(side),status=String(trade.status||"OPEN").toUpperCase(),symbol=trade.symbol||plan.symbol||"Paper trade",label=assetLabel(symbol,trade.label||plan.label),strategy=strategyLabel(plan.strategy||trade.strategy),entry=plan.entry??trade.entry,pnl=trade.pnl;return `<article class="trade-row ${d.cls}" data-trade-index="${index}"><div class="trade-row-main"><div class="trade-row-identity"><span class="direction-icon">${d.icon}</span><div><strong>${escapeHtml(label)}</strong><small>${escapeHtml(strategy)} · ${escapeHtml(side||"—")}</small></div></div><div class="trade-row-price"><span>Entry</span><b>${price(entry)}</b></div><div class="trade-row-price"><span>${status==="CLOSED"?"P/L":"Risk"}</span><b class="${status==="CLOSED"&&Number(pnl)<0?"negative":status==="CLOSED"&&Number(pnl)>=0?"positive":""}">${status==="CLOSED"?inr(pnl):inr(plan.planned_risk??trade.planned_risk)}</b></div><span class="trade-status ${status.toLowerCase()}">${status}</span><button class="trade-detail-button" type="button" data-trade-index="${index}" aria-label="View ${escapeHtml(label)} details">View</button></div></article>`;}
function renderScanStatus(){const scan=state.data?.scan||{},status=String(scan.status||"NOT_RUN").toUpperCase();const el=$("scanSummary");if(!el)return;if(status==="COMPLETE"){el.innerHTML=`<b>${escapeHtml(timestamp(scan.at))}</b><small> · ${number(scan.checked,0)} checked · ${number(scan.directional,0)} directional · ${number(scan.sent,0)} dispatched</small>`;}else{el.innerHTML=`<b>No completed scan recorded since runtime start.</b>`;}}
function signalDateKey(date){return `signal-date:${date}`;}
function renderSignalDateGroups(signals){const groups=new Map();signals.forEach(signal=>{const date=dateKey(signal.timestamp);if(!groups.has(date))groups.set(date,[]);groups.get(date).push(signal);});const ordered=[...groups.entries()].sort((a,b)=>b[0].localeCompare(a[0]));if(!state.groupInit.has("signal")){state.groupInit.add("signal");if(!state.signalDates.size&&ordered[0])state.signalDates.add(signalDateKey(ordered[0][0]));}return ordered.map(([date,rows])=>{const key=signalDateKey(date),open=state.signalDates.has(key),buys=rows.filter(x=>String(x.signal||x.direction||"").toUpperCase()==="BUY").length,sells=rows.length-buys;return `<section class="signal-date-group ${open?"is-open":""}"><button class="signal-date-toggle" type="button" data-signal-date="${escapeHtml(key)}" aria-expanded="${open}"><span><b>${escapeHtml(dateLabel(date))}</b><small>${rows.length} signal${rows.length===1?"":"s"} · ${buys} BUY · ${sells} SELL</small></span><i aria-hidden="true" class="collapse-control ${open?"is-open":""}"></i></button>${open?`<div class="signal-date-rows">${rows.map(signalCard).join("")}</div>`:""}</section>`;}).join("");}
function renderSignals(){const all=canonicalSignals(),signals=all;$("signalsResultCount").textContent=`${signals.length} signal${signals.length===1?"":"s"}`;$("signalsList").innerHTML=signals.length?renderSignalDateGroups(signals):empty("No signals yet","◇","Detected BUY and SELL signals will appear here when the runtime produces them.");}
function historyDateKey(prefix,date){return `history-${prefix}-date:${date}`;}
function scanDateValue(row){return row?.completed_at||row?.created_at||row?.timestamp||row?.run_at||row?.started_at||row?.updated_at;}
function renderHistoryScanRow(row){
  const p=row?.payload||{};
  const strategy=strategyLabel(row?.strategy_id||row?.strategy||"Strategy");
  const status=String(row?.status||"RECORDED").toUpperCase();
  const checked=number(p.checked,0), directional=number(p.directional,0), sent=number(p.sent,0), errors=number(p.errors,0);
  const stamp=timestamp(scanDateValue(row));
  return `<article class="history-scan-row">
    <div class="history-scan-head">
      <div class="history-scan-identity">
        <strong>${escapeHtml(strategy)}</strong>
        <small>${escapeHtml(stamp)}</small>
      </div>
      <span class="history-scan-status">${escapeHtml(status)}</span>
    </div>
    <div class="history-scan-metrics" aria-label="Scan results">
      <span><b>${checked}</b> checked</span>
      <span><b>${directional}</b> directional</span>
      <span><b>${sent}</b> sent</span>
      <span><b>${errors}</b> errors</span>
    </div>
  </article>`;
}
function renderHistoryDateGroups(rows,kind){const groups=new Map();rows.forEach(row=>{const date=dateKey(kind==="trade"?tradeDateValue(row.trade):scanDateValue(row.scan));if(!groups.has(date))groups.set(date,[]);groups.get(date).push(row);});const ordered=[...groups.entries()].sort((a,b)=>b[0].localeCompare(a[0])),openSet=kind==="trade"?state.historyTradeDates:state.historyScanDates;if(!state.groupInit.has(kind)){state.groupInit.add(kind);if(!openSet.size&&ordered[0]&&kind==="trade")openSet.add(historyDateKey(kind,ordered[0][0]));}return ordered.map(([date,items])=>{const key=historyDateKey(kind,date),open=openSet.has(key),noun=kind==="trade"?"trade":"scan";return `<section class="history-date-group ${open?"is-open":""}"><button class="history-date-toggle" type="button" data-history-date="${escapeHtml(key)}" data-history-kind="${kind}" aria-expanded="${open}"><span><b>${escapeHtml(dateLabel(date))}</b><small>${items.length} ${noun}${items.length===1?"":"s"}</small></span><i aria-hidden="true" class="collapse-control ${open?"is-open":""}"></i></button>${open?`<div class="history-date-rows">${kind==="trade"?items.map(row=>renderTradeRow(row.trade,row.index)).join(""):items.map(row=>renderHistoryScanRow(row.scan)).join("")}</div>`:""}</section>`;}).join("");}
function renderOpenHistoryRow(trade,index){
  const plan=trade?.plan||trade;
  const side=String(plan.side||trade.type||"").toUpperCase();
  const d=direction(side);
  const symbol=trade.symbol||plan.symbol||"Paper trade";
  const label=assetLabel(symbol,trade.label||plan.label);
  const strategy=strategyLabel(plan.strategy||trade.strategy);
  const risk=trade.planned_risk??plan.planned_risk;
  return `<article class="live-trade-row ${d.cls}">
    <div>
      <strong>${escapeHtml(label)}</strong>
      <small>${escapeHtml(strategy)} · ${escapeHtml(side||"—")} · Entry ${price(plan.entry??trade.entry)}</small>
    </div>
    <div><span>Risk</span><b>${inr(risk)}</b></div>
    <div><span>Opened</span><b>${escapeHtml(timestamp(trade.opened_at||trade.created_at))}</b></div>
    <span class="live-open-badge">OPEN</span>
    <button class="trade-detail-button" type="button" data-trade-index="${index}" aria-label="View ${escapeHtml(label)} details">View</button>
  </article>`;
}
function renderHistory(){
  const data=state.data||{};
  const trades=Array.isArray(data.trades)?data.trades:[];
  const closedRows=trades.map((trade,index)=>({trade,index})).filter(row=>String(row.trade?.status||"").toUpperCase()==="CLOSED");
  const openRows=trades.map((trade,index)=>({trade,index})).filter(row=>String(row.trade?.status||"").toUpperCase()==="OPEN");
  const closed=closedRows.map(row=>row.trade);
  const pnlValues=closed.map(t=>Number(t?.pnl)).filter(Number.isFinite);
  const winners=pnlValues.filter(v=>v>0).length;
  const dates=closedRows.map(row=>dateKey(tradeDateValue(row.trade))).filter(x=>x!=="unknown").sort();
  const latestDate=dates.length?dates[dates.length-1]:null;
  const dailyRows=latestDate?closedRows.filter(row=>dateKey(tradeDateValue(row.trade))===latestDate):[];
  const dailyPnl=dailyRows.reduce((sum,row)=>sum+(Number(row.trade?.pnl)||0),0);

  const closedCount=$("historyClosedCount");
  const dailyPnlEl=$("historyDailyPnl");
  const winRate=$("historyWinRate");
  const resultCount=$("historyResultCount");
  const list=$("historyList");
  const openList=$("historyOpenTrades");
  const scanList=$("historyScanHistory");

  if(closedCount)closedCount.textContent=String(closedRows.length);
  if(dailyPnlEl)dailyPnlEl.textContent=latestDate?inr(dailyPnl):"—";
  if(winRate)winRate.textContent=pnlValues.length?Math.round(winners/pnlValues.length*100)+"%":"—";
  if(resultCount)resultCount.textContent=`${closedRows.length} trade${closedRows.length===1?"":"s"}`;

  // Clear every loading placeholder first. A malformed optional row must never
  // leave the History page looking permanently stuck.
  if(list){
    try{
      list.innerHTML=closedRows.length
        ?renderHistoryDateGroups(closedRows,"trade")
        :empty("No completed trades","◷","Completed paper trades will appear here grouped by date.");
    }catch(error){
      console.error("History completed trades render failed",error);
      list.innerHTML=empty("History unavailable","!","The completed-trade snapshot could not be rendered.");
    }
  }

  if(openList){
    try{
      openList.innerHTML=openRows.length
        ?openRows.map(row=>renderOpenHistoryRow(row.trade,row.index)).join("")
        :`<div class="empty-state history-empty-state"><span>—</span><strong>No open positions</strong><small>There are no active paper trades in the current snapshot.</small></div>`;
    }catch(error){
      console.error("History open positions render failed",error);
      openList.innerHTML=empty("Open positions unavailable","!","The current paper-trade snapshot could not be rendered.");
    }
  }

  const scans=Array.isArray(data.scan_history)?data.scan_history:[];
  const scanRows=scans.map(scan=>({scan})).filter(row=>scanDateValue(row.scan));
  if(scanList){
    try{
      scanList.innerHTML=scanRows.length
        ?renderHistoryDateGroups(scanRows,"scan")
        :`<div class="empty-state history-empty-state"><span>—</span><strong>No scan history</strong><small>Persisted runtime scans will appear here when completed runs are recorded.</small></div>`;
    }catch(error){
      console.error("History scan history render failed",error);
      scanList.innerHTML=empty("Scan history unavailable","!","The persisted scan snapshot could not be rendered.");
    }
  }
}
function calendarDayKey(day){return `calendar-day:${day}`;}
function renderCalendar(){
  const calendar=state.calendar||{},days=Array.isArray(calendar.days)?calendar.days:[],items=Array.isArray(calendar.items)?calendar.items:[],status=String(calendar.status||"UNKNOWN").toUpperCase(),available=["ONLINE","CACHED"].includes(status),counts=calendar.counts||{};
  const total=Number(counts.high||0)+Number(counts.medium||0)+Number(counts.low||0)+Number(counts.holiday||0);
  $("calendarStatus").innerHTML=`<span class="inline-status"><span class="news-dot ${available?"online":"offline"}"></span><b>${escapeHtml(status)}</b><small>${escapeHtml(calendar.message||"No calendar status available.")}${calendar.fetched_at?` · Saved ${escapeHtml(timestamp(calendar.fetched_at))}`:""}</small></span>`;
  $("impactCountall").textContent=number(total||items.length,0);
  $("impactCounthigh").textContent=number(counts.high||0,0);
  $("impactCountmedium").textContent=number(counts.medium||0,0);
  $("impactCountother").textContent=number(Number(counts.low||0)+Number(counts.holiday||0),0);
  $("calendarResultCount").textContent=`${items.length} event${items.length===1?"":"s"} · ${days.length} date${days.length===1?"":"s"}`;
  $("calendarItems").innerHTML=days.length?calendarDateGroups(days):empty(status==="OFFLINE"?"Calendar source unavailable":"No upcoming events","◉",calendar.message||"The calendar cache has no upcoming events yet.");
}
function calendarDateGroups(days){
  if(!state.calendarDates)state.calendarDates=new Set();
  if(!state.groupInit.has("calendar")){state.groupInit.add("calendar");if(days[0])state.calendarDates.add(calendarDayKey(days[0].date));}
  return days.map((day,index)=>{
    const key=calendarDayKey(day.date),open=state.calendarDates.has(key),items=Array.isArray(day.items)?day.items:[];
    const today=index===0?"TODAY · ":"";
    return `<section class="calendar-date-group ${open?"is-open":""}">
      <button class="calendar-date-toggle" type="button" data-calendar-date-group="${escapeHtml(key)}" aria-expanded="${open}">
        <span><b>${today}${escapeHtml(day.label||dateLabel(day.date))}</b><small>${items.length} scheduled event${items.length===1?"":"s"} · High ${number(day.counts?.high,0)} · Medium ${number(day.counts?.medium,0)}</small></span>
        <i aria-hidden="true" class="collapse-control ${open?"is-open":""}"></i>
      </button>
      ${open?`<div class="calendar-date-events">${calendarTimeline(items)}</div>`:""}
    </section>`;
  }).join("");
}
function calendarTimeline(items){
  const rank={High:0,Medium:1,Low:2,Holiday:3};
  const timeValue=value=>{const s=String(value||"").trim();const m=s.match(/(\d{1,2}):(\d{2})/);return m?Number(m[1])*60+Number(m[2]):-1;};
  return [...items].sort((a,b)=>timeValue(a.time)-timeValue(b.time)||((rank[a.impact]??9)-(rank[b.impact]??9))).map(calendarCard).join("");
}
function calendarCard(item,index){
  const key=keyFor("calendar",item,index),impact=String(item.impact||"Low").toLowerCase(),open=state.expanded.has(key);
  const details=open?`<div class="calendar-details"><span>Actual <b>${escapeHtml(item.actual||"—")}</b></span><span>Forecast <b>${escapeHtml(item.forecast||"—")}</b></span><span>Previous <b>${escapeHtml(item.previous||"—")}</b></span></div>`:"";
  return `<article class="calendar-item impact-${escapeHtml(impact)} ${open?"expanded":""}">
    <div class="calendar-event">
      <div class="calendar-meta">
        <strong class="calendar-time-value">${escapeHtml(item.time||"All day")}</strong>
        <i class="news-dot impact-${escapeHtml(impact)}" aria-hidden="true"></i>
        <span class="currency-code">${escapeHtml(item.currency||"ALL")}</span>
        <b class="impact-pill ${escapeHtml(impact)}">${escapeHtml(item.impact||"Low")}</b>
        ${expandButton(key,"event")}
      </div>
      <strong class="calendar-title">${escapeHtml(item.title||"Economic event")}</strong>
      ${details}
    </div>
  </article>`;
}
function renderTools(){const data=state.data||{},universe=Array.isArray(data.universe?.symbols)?data.universe.symbols:[],strategies=Array.isArray(data.strategies)?data.strategies:[],accounts=Array.isArray(data.accounts?.data)?data.accounts.data:[];const strategySelect=$("backtestStrategy"),currentStrategy=strategySelect.value;strategySelect.innerHTML=strategies.map(strategy=>`<option value="${escapeHtml(strategy.id)}">${escapeHtml(strategy.name)} · v${escapeHtml(strategy.version)}</option>`).join("");if([...strategySelect.options].some(o=>o.value===currentStrategy))strategySelect.value=currentStrategy;const assets=supportedBacktestAssets(strategySelect.value),select=$("backtestSymbol"),current=select.value,groups={};assets.forEach(asset=>(groups[asset.group]??=[]).push(asset));select.innerHTML=Object.entries(groups).map(([group,rows])=>`<optgroup label="${escapeHtml(group)}">${rows.map(asset=>`<option value="${escapeHtml(asset.key||asset.ticker)}">${escapeHtml(asset.label)}</option>`).join("")}</optgroup>`).join("");if([...select.options].some(o=>o.value===current))select.value=current;const assetGroups={
    "Indian Equities":[],
    "Indices":[],
    "Commodities":[],
    "Crypto":[],
    "Forex":[]
  };
  universe.forEach(s=>{
    const raw=String(s||"").toUpperCase(),label=assetLabel(s,s),upper=String(label).toUpperCase();
    const group=raw.includes("NIFTY")||upper.includes("NIFTY")?"Indices":raw.includes("GOLD")||upper.includes("GOLD")?"Commodities":raw.includes("BTC")||upper.includes("BITCOIN")?"Crypto":raw.includes("/")||upper.includes("EUR/")||upper.includes("GBP/")||upper.includes("AUD/")||upper.includes("USD/")||upper.includes("NZD/")?"Forex":"Indian Equities";
    assetGroups[group].push(label);
  });
  $("universeGrid").innerHTML=Object.entries(assetGroups).filter(([,rows])=>rows.length).map(([group,rows])=>`<section class="asset-category"><span class="asset-category-label">${escapeHtml(group)}</span><div class="asset-category-items">${rows.map(label=>`<span>${escapeHtml(label)}</span>`).join("")}</div></section>`).join("");$("accountsGrid").innerHTML=accounts.map(a=>`<article><b>${escapeHtml(String(a.name).toUpperCase())}</b><span>${inr(a.balance)} · ${number(a.trades_today,0)}/${number(a.daily_trade_limit,0)} trades</span><small>${inr(a.remaining_planned_risk)} planned risk remaining</small></article>`).join("");$("versionText").textContent=`v${data.version||"2.0.0"}`;$("whatsNewList").innerHTML=(data.whats_new||[]).map(item=>`<li>${escapeHtml(item)}</li>`).join("");$("candleSchedule").innerHTML=["10:15|First close","11:15|Hourly close","12:15|Hourly close","13:15|Hourly close","14:15|Hourly close","15:15|Final close"].map(item=>{const [time,label]=item.split("|");return `<span><b>${time}</b><small>${label}</small></span>`;}).join("");$("diagnostics").innerHTML=`<article class="compact-metric"><span>API</span><b>Connected</b></article><article class="compact-metric"><span>Provider</span><b>${escapeHtml(data.system?.provider||data.health?.provider||"UNKNOWN")}</b></article><article class="compact-metric"><span>Timezone</span><b>${escapeHtml(data.system?.timezone||CONFIG.timezone)}</b></article><article class="compact-metric"><span>Snapshot</span><b>${escapeHtml(timestamp(data.generated_at))}</b></article>`;if(!state.settingsDirty){if(!state.settings)loadSettings();}else if(state.settingsMessage?.kind!=="error")settingsStatus("Unsaved changes. Save to apply them to the running bot.","info");$$('[data-theme-choice]').forEach(b=>{b.classList.add("chip-option");b.classList.remove("appearance-option");});$$('[data-style-choice]').forEach(b=>{b.classList.add("chip-option");b.classList.remove("appearance-option");});$$('[data-accent-choice]').forEach(b=>{b.classList.add("chip-option");b.classList.remove("appearance-option");});applyAppearanceControls();if(state.backtest)renderBacktest(state.backtest);}
function backtestMetricLabel(key){return ({return_pct:"Return",max_drawdown_pct:"Max drawdown",sharpe:"Sharpe",sortino:"Sortino",win_rate_pct:"Win rate",profit_factor:"Profit factor",number_of_trades:"Trades",average_trade:"Average trade",max_losing_streak:"Max losing streak",exposure_pct:"Exposure",risk_adjusted_performance:"Risk-adjusted performance"})[key]||key.replaceAll("_"," ");}
function formatBacktestMetric(key,value){const n=Number(value);if(!Number.isFinite(n))return "—";if(["return_pct","max_drawdown_pct","win_rate_pct","exposure_pct"].includes(key))return `${number(n,2)}%`;if(key==="average_trade")return inr(n);if(["number_of_trades","max_losing_streak"].includes(key))return number(n,0);return number(Math.max(-9999,Math.min(9999,n)),2);}
function renderBacktest(result){const status=$("backtestStatus"),box=$("backtestResults");if(!result){box.hidden=true;return;}if(result.ok===false){status.className="backtest-status error";status.textContent=`Backtest failed: ${result.error||"Unknown error"}`;box.hidden=true;return;}status.className="backtest-status success";status.textContent=`${result.strategy} · ${result.asset?.label||result.symbol} · ${result.period} · ${number(result.candle_count,0)} candles`;const curve=Array.isArray(result.equity_curve)?result.equity_curve:[];const trades=Array.isArray(result.trades)?result.trades:[];const metrics=Object.entries(result.metrics||{}).filter(([key])=>!["rating","rating_label","breakdown"].includes(key));box.innerHTML=`<section class="backtest-section backtest-overview-section"><div class="backtest-summary"><div><span>START</span><b>${inr(curve[0]?.equity||100000)}</b></div><div><span>END</span><b>${inr(curve[curve.length-1]?.equity||100000)}</b></div><div><span>TRADES</span><b>${number(result.trades_taken,0)}</b></div><div><span>RETURN</span><b>${formatBacktestMetric("return_pct",result.metrics?.return_pct)}</b></div></div></section><section class="backtest-section backtest-curve-section"><div class="chart-head"><div><strong>Equity curve</strong><small>Paper account value after each completed backtest trade</small></div><span>${trades.length} trade${trades.length===1?"":"s"}</span></div>${curve.length?renderEquityLine(curve,{label:"Backtest equity curve"}):empty("No completed trades","◇","The selected period produced no completed trades to plot.")}</section><section class="backtest-section backtest-performance-section"><div class="backtest-section-heading"><div><span class="eyebrow">PERFORMANCE</span><h3>Results</h3></div><span class="backtest-rating">${escapeHtml(result.metrics?.rating_label||result.metrics?.rating||"—")}</span></div><div class="backtest-metrics">${metrics.map(([key,value])=>`<div><span>${escapeHtml(backtestMetricLabel(key))}</span><b title="${escapeHtml(formatBacktestMetric(key,value))}">${escapeHtml(formatBacktestMetric(key,value))}</b></div>`).join("")}</div></section><section class="backtest-section backtest-trades-section"><div class="backtest-section-heading"><div><span class="eyebrow">EXECUTION</span><h3>Completed trades</h3></div><span>${trades.length} recorded</span></div><div class="backtest-trades">${trades.length?trades.slice().reverse().map(trade=>{const d=direction(trade.direction),pnl=Number(trade.pnl);return `<article class="backtest-trade-row ${d.cls}"><span class="backtest-trade-side ${d.cls}">${d.text}</span><div><b>${escapeHtml(timestamp(trade.timestamp))}</b><small>Entry ${price(trade.entry)} · Exit ${price(trade.exit)} · ${number(trade.bars_held,0)} bars</small></div><strong class="${pnl>=0?"positive":"negative"}">${inr(pnl)}</strong></article>`;}).join(""):empty("No completed trades","◷","Trades will appear here separately from performance metrics.")}</div></section>`;box.hidden=false;}
async function runBacktest(){const strategy=$("backtestStrategy").value,symbol=$("backtestSymbol").value,period=$("backtestPeriod").value,button=$("runBacktestButton");button.disabled=true;$("backtestStatus").className="backtest-status loading";$("backtestStatus").textContent="Fetching real Yahoo candles and running the canonical strategy…";try{const response=await fetch(`/api/backtest?${new URLSearchParams({strategy,symbol,period})}`,{cache:"no-store"});const result=await readJsonResponse(response,"Backtest API");if(result.ok===false)throw new Error(result.error||"Backtest failed");state.backtest=result;renderBacktest(result);}catch(error){state.backtest={ok:false,error:error.message};renderBacktest(state.backtest);}finally{button.disabled=false;}}
async function loadCalendar(){const impact=state.calendarImpacts.has("All")?"All":[...state.calendarImpacts].join(",");$("calendarItems").innerHTML=empty("Loading calendar…","◉","Reading the saved Forex Factory feed.");try{const url=`/api/calendar?${new URLSearchParams({date:state.calendarDate,impact})}`;const response=await fetch(url,{cache:"no-store"});state.calendar=await readJsonResponse(response,"Calendar API");renderCalendar();}catch(error){state.calendar={status:"OFFLINE",source:"Forex Factory",message:error.message,items:[],counts:{}};renderCalendar();}}
async function showConnectionStatus(online,message=""){const banner=$("connectionBanner"),status=$("systemStatus"),badge=$("systemStatusBadge");if(banner){banner.hidden=online;if(!online)banner.textContent=message||"Dashboard connection problem.";}if(status)status.textContent=online?"ONLINE":"OFFLINE";if(badge)badge.classList.toggle("offline",!online);}
function renderSafely(name,fn){try{fn();}catch(error){console.error(`Dashboard render failed: ${name}`,error);}}
function announceSnapshot(payload){const region=$("dashboardAnnouncer");if(!region)return;const c=payload?.counts||{};const health=payload?.health||{};const scan=payload?.scan||{};const message=`Updated. ${number(c.signals,0)} signals, ${number(c.directional_signals,0)} directional, ${number(c.fresh_directional,0)} fresh. ${number(c.open_trades,0)} open trades, ${number(c.closed_trades,0)} closed. Scan ${String(scan.status||"NOT_RUN").toLowerCase()}, ${number(scan.checked,0)} assets checked. Delivery ${String(health.telegram||"DISABLED").toLowerCase()}.`;if(region.textContent!==message)region.textContent=message;}async function loadDashboard(){try{const response=await fetch(`${CONFIG.apiUrl}?t=${Date.now()}`,{cache:"no-store"});if(!response.ok)throw new Error(`Dashboard API ${response.status}`);const payload=await readJsonResponse(response,"Dashboard API");if(payload.ok===false)throw new Error(payload?.error||"Dashboard API returned an invalid snapshot.");state.data=payload;state.lastUpdate=payload.generated_at||new Date().toISOString();showConnectionStatus(true);announceSnapshot(payload);renderSafely("overview",renderOverview);renderSafely("scanStatus",renderScanStatus);renderSafely("signals",renderSignals);renderSafely("history",renderHistory);renderSafely("tools",renderTools);if(state.activePage==="calendar")renderSafely("calendar",loadCalendar);}catch(error){console.error("Dashboard load failed",error);showConnectionStatus(false,`Dashboard connection problem: ${error.message}`);}}
function setPage(page){
  state.activePage=page;
  $$(".page").forEach(el=>el.classList.toggle("active",el.id===`page-${page}`));
  $$(".nav-button").forEach(el=>el.classList.toggle("active",el.dataset.page===page));
  if(page==="history"&&state.data)renderSafely("history",renderHistory);
  if(page==="calendar")loadCalendar();
  window.scrollTo({top:0,behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth"});
}
function resolveTheme(theme){return theme==="system"?(window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"):theme;}function applyTheme(theme){const choice=["light","dark","system"].includes(theme)?theme:"light";document.documentElement.dataset.theme=resolveTheme(choice);document.documentElement.dataset.themePref=choice;localStorage.setItem("mavis-theme",choice);applyAppearanceControls();}
function applyStyle(style){const value=style==="neo"?"neo":"modern";document.documentElement.dataset.style=value;localStorage.setItem("mavis-style",value);applyAppearanceControls();}
function applyAppearanceControls(){$$('[data-theme-choice]').forEach(b=>{const active=b.dataset.themeChoice===(document.documentElement.dataset.themePref||document.documentElement.dataset.theme);b.classList.toggle("active",active);b.setAttribute("aria-pressed",String(active));});$$('[data-style-choice]').forEach(b=>{const active=b.dataset.styleChoice===document.documentElement.dataset.style;b.classList.toggle("active",active);b.setAttribute("aria-pressed",String(active));});$$('[data-accent-choice]').forEach(b=>{const active=b.dataset.accentChoice===document.documentElement.dataset.accent;b.classList.toggle("active",active);b.setAttribute("aria-pressed",String(active));});const compact=localStorage.getItem("mavis-compact")==="true",motion=localStorage.getItem("mavis-reduce-motion")==="true";document.documentElement.dataset.compact=compact?"true":"false";document.documentElement.dataset.reduceMotion=motion?"true":"false";const c=$("compactModeToggle"),m=$("reduceMotionToggle");if(c){c.classList.toggle("active",compact);c.setAttribute("aria-pressed",String(compact));}if(m){m.classList.toggle("active",motion);m.setAttribute("aria-pressed",String(motion));}}
function applyAccent(accent){const value=["emerald","indigo","amber","rose","cyan"].includes(accent)?accent:"emerald";document.documentElement.dataset.accent=value;localStorage.setItem("mavis-accent",value);applyAppearanceControls();}
function initAppearance(){const theme=localStorage.getItem("mavis-theme")||"light",style=localStorage.getItem("mavis-style")||"modern";document.documentElement.dataset.style=style;const accent=localStorage.getItem("mavis-accent");document.documentElement.dataset.accent=["emerald","indigo","amber","rose","cyan"].includes(accent)?accent:"emerald";applyTheme(theme);}
function bindEvent(id,event,handler){const el=$(id);if(!el){console.warn(`Dashboard control missing: #${id}`);return;}el.addEventListener(event,handler);}
function openReleaseModal(){const modal=$("releaseModal");if(!modal)return;modal.classList.add("open");document.body.classList.add("release-open");const close=$("releaseModalClose");if(close)close.focus();}
function closeReleaseModal(){const modal=$("releaseModal");if(!modal||!modal.classList.contains("open"))return;modal.classList.remove("open");document.body.classList.remove("release-open");}
function syncToolCollapseControl(card){const control=card?.querySelector(".collapse-control");if(!control)return;const open=card.classList.contains("is-open");control.setAttribute("aria-expanded",String(open));control.setAttribute("aria-label",(open?"Collapse ":"Expand ")+(card.dataset.toolKey||"section"));control.classList.toggle("is-open",open);}
function syncAllToolCollapseControls(){document.querySelectorAll("[data-tool-collapse]").forEach(syncToolCollapseControl);}
function bindEvents(){
$$('[data-page]').forEach(button=>button.addEventListener("click",()=>setPage(button.dataset.page)));
$$('[data-page-link]').forEach(button=>button.addEventListener("click",()=>setPage(button.dataset.pageLink)));
bindEvent("refreshButton","click",loadDashboard);
bindEvent("signalsRefreshButton","click",loadDashboard);
bindEvent("historyRefreshButton","click",loadDashboard);
bindEvent("themeToggle","click",()=>applyTheme(document.documentElement.dataset.theme==="dark"?"light":"dark"));
$$('[data-theme-choice]').forEach(button=>button.addEventListener("click",()=>applyTheme(button.dataset.themeChoice)));
$$('[data-style-choice]').forEach(button=>button.addEventListener("click",()=>applyStyle(button.dataset.styleChoice)));
$$('[data-accent-choice]').forEach(button=>button.addEventListener("click",()=>applyAccent(button.dataset.accentChoice)));
bindEvent("compactModeToggle","click",()=>{const next=localStorage.getItem("mavis-compact")!=="true";localStorage.setItem("mavis-compact",String(next));applyAppearanceControls();});
bindEvent("reduceMotionToggle","click",()=>{const next=localStorage.getItem("mavis-reduce-motion")!=="true";localStorage.setItem("mavis-reduce-motion",String(next));applyAppearanceControls();});

bindEvent("runBacktestButton","click",runBacktest);
bindEvent("settingsStartHour","change",markSettingsDirty);
bindEvent("settingsEndHour","change",markSettingsDirty);
bindEvent("saveSettingsButton","click",saveSettings);
bindEvent("resetSettingsButton","click",resetSettings);
bindEvent("addAccountButton","click",addAccount);
bindEvent("addAssetButton","click",addAsset);
bindEvent("settingsAccounts","input",event=>{
  const field=event.target.closest("[data-account-field]");if(!field)return;
  const account=state.settings?.accounts[Number(field.dataset.accountIndex)];if(!account)return;
  const key=field.dataset.accountField;
  account[key]=key==="daily_trade_limit"?Math.round(Number(field.value)||0):Number(field.value);
  markSettingsDirty();renderSettings();
});
bindEvent("settingsAssets","input",event=>{
  const field=event.target.closest("[data-asset-field]");if(!field)return;
  const asset=state.settings?.assets[Number(field.dataset.assetIndex)];if(!asset)return;
  asset[field.dataset.assetField]=field.value;
  if(field.dataset.assetField==="group"){asset.currency=field.value==="Global Markets"?"USD":"INR";asset.sweep_timeframe=field.value==="NSE Indices"?"1H":"4H";}
  markSettingsDirty();renderSettings();
});
bindEvent("settingsAssets","click",event=>{
  const chip=event.target.closest("[data-asset-strategy]");
  if(chip){
    const asset=state.settings?.assets[Number(chip.dataset.assetIndex)];if(!asset)return;
    const id=chip.dataset.assetStrategy;
    asset.strategies=asset.strategies.includes(id)?asset.strategies.filter(x=>x!==id):[...asset.strategies,id];
    markSettingsDirty();renderSettings();return;
  }
  const remove=event.target.closest("[data-remove-asset]");
  if(remove){state.settings.assets.splice(Number(remove.dataset.removeAsset),1);markSettingsDirty();renderSettings();}
});
bindEvent("settingsAccounts","click",event=>{
  const remove=event.target.closest("[data-remove-account]");
  // A rule for a deleted account would orphan it, so both go together.
  if(remove){const name=state.settings.accounts[Number(remove.dataset.removeAccount)]?.name;state.settings.accounts.splice(Number(remove.dataset.removeAccount),1);state.settings.rules=state.settings.rules.filter(r=>r.account!==name);markSettingsDirty();renderSettings();}
});
bindEvent("settingsRules","click",event=>{
  const chip=event.target.closest("[data-settings-kind]");
  if(chip){settingsToggle(chip.dataset.settingsKind,Number(chip.dataset.settingsIndex),chip.dataset.settingsValue);renderSettings();return;}
  const move=event.target.closest("[data-settings-move]");
  if(move&&!move.disabled){settingsMove(Number(move.dataset.settingsIndex),Number(move.dataset.settingsMove));renderSettings();}
});
bindEvent("backtestStrategy","change",()=>{state.backtest=null;renderTools();});
bindEvent("calendarRefreshButton","click",loadCalendar);document.addEventListener("keydown",event=>{if(event.key==="Escape"){closeTradeDrawer();closeReleaseModal();return;}if(event.key!=="Enter"&&event.key!==" ")return;const row=event.target.closest(".card-main[data-expand]");if(!row||row!==event.target)return;event.preventDefault();const rowKey=row.dataset.expand;row.click();const restored=[...document.querySelectorAll(".card-main[data-expand]")].find(n=>n.dataset.expand===rowKey);if(restored)restored.focus();});
document.addEventListener("click",event=>{const releaseButton=event.target.closest("#whatsNewButton");if(releaseButton){event.preventDefault();openReleaseModal();return;}const releaseClose=event.target.closest("#releaseModalClose");if(releaseClose){event.preventDefault();closeReleaseModal();return;}if(event.target.id==="releaseModal"){closeReleaseModal();return;}const toolToggle=event.target.closest("[data-tool-toggle]");if(toolToggle){event.preventDefault();const card=toolToggle.closest("[data-tool-collapse]");if(card){card.classList.toggle("is-open");syncToolCollapseControl(card);}return;}const tradeTrigger=event.target.closest("[data-trade-index]");if(tradeTrigger){const trades=Array.isArray(state.data?.trades)?state.data.trades:[],trade=trades[Number(tradeTrigger.dataset.tradeIndex)];if(trade){event.preventDefault();openTradeDetail(trade);}return;}const calendarDateGroup=event.target.closest("[data-calendar-date-group]");if(calendarDateGroup){const key=calendarDateGroup.dataset.calendarDateGroup;if(state.calendarDates.has(key))state.calendarDates.delete(key);else state.calendarDates.add(key);renderSafely("calendar",renderCalendar);return;}const signalDate=event.target.closest("[data-signal-date]");if(signalDate){const key=signalDate.dataset.signalDate;if(state.signalDates.has(key))state.signalDates.delete(key);else state.signalDates.add(key);renderSafely("signals",renderSignals);return;}const historyDate=event.target.closest("[data-history-date]");if(historyDate){const kind=historyDate.dataset.historyKind;const key=historyDate.dataset.historyDate;const set=kind==="scan"?state.historyScanDates:state.historyTradeDates;if(set.has(key))set.delete(key);else set.add(key);renderSafely("history",renderHistory);return;}const trigger=event.target.closest("[data-expand]");if(!trigger)return;const key=trigger.dataset.expand;if(state.expanded.has(key))state.expanded.delete(key);else state.expanded.add(key);renderSafely("overview",renderOverview);renderSafely("signals",renderSignals);renderSafely("history",renderHistory);if(state.calendar)renderSafely("calendar",renderCalendar);});
}
// ---------------------------------------------------------------------------
// Bot settings editor (Tools > Accounts, assets and routing)
// ---------------------------------------------------------------------------
// These values decide which account takes a real trade and on how much
// capital, so they live on the server. `state.settings` is the working copy the
// editor mutates; it is only replaced when there are no unsaved changes, so
// the 30s dashboard refresh can never discard an edit in progress.
//
// Declared below bindEvents() on purpose: every function here is hoisted, and
// keeping the block after bindEvents keeps loadDashboard()'s first call site
// inside bootstrapDashboard().
const ROUTING_WINDOWS=[["null","Any time"],["true","Inside session"],["false","Outside session"]];
const BUILTIN_ACCOUNTS=["macro","nifty","ny_session","sweep_4h"];
let settingsRequested=false;

function settingsModel(payload){
  const s=payload||{};
  return{
    accounts:(Array.isArray(s.accounts)?s.accounts:[]).map(a=>({name:String(a.name||""),starting_balance:Number(a.starting_balance)||0,daily_trade_limit:Number(a.daily_trade_limit)||1,risk_per_trade:Number(a.risk_per_trade)||0})),
    assets:(Array.isArray(s.assets)?s.assets:[]).map(a=>({symbol:String(a.symbol||""),label:String(a.label||""),yahoo_symbol:String(a.yahoo_symbol||""),market:String(a.market||""),asset_type:String(a.asset_type||""),group:String(a.group||""),currency:String(a.currency||"INR"),sweep_timeframe:String(a.sweep_timeframe||"4H"),strategies:Array.isArray(a.strategies)?a.strategies.slice():[]})),
    session:{timezone:s.session?.timezone||"America/New_York",start_hour:Number(s.session?.start_hour)||0,end_hour:Number(s.session?.end_hour)||0,active_now:!!s.session?.active_now},
    rules:(Array.isArray(s.rules)?s.rules:[]).map(r=>({account:String(r.account||""),strategies:Array.isArray(r.strategies)?r.strategies.slice():null,asset_groups:Array.isArray(r.asset_groups)?r.asset_groups.slice():null,in_ny_session:r.in_ny_session===true?true:r.in_ny_session===false?false:null})),
    strategies:(Array.isArray(s.options?.strategies)?s.options.strategies:[]).map(String),
    strategyNames:(s.options?.strategy_names)||{},
    groups:(Array.isArray(s.options?.account_groups)?s.options.account_groups:[]).map(String),
    limits:s.options?.limits||{}};
}
async function loadSettings(){
  if(state.settingsDirty||settingsRequested)return;
  settingsRequested=true;
  try{
    const response=await fetch("/api/settings",{cache:"no-store"});
    const payload=await readJsonResponse(response,"Settings API");
    if(payload.ok===false)throw new Error(payload.error||"Settings API failed");
    state.settings=settingsModel(payload.settings);
    renderSettings();
    settingsStatus("Saved on the server and applied to the running bot. Nothing here changes a trade until you save.","info");
  }catch(error){settingsStatus(error.message,"error");}
  finally{settingsRequested=false;}
}
function paintSettingsStatus(){
  const el=$("settingsStatus"),message=state.settingsMessage;if(!el||!message)return;
  el.className=`backtest-status${message.kind==="info"?"":` ${message.kind}`}`;
  el.textContent=message.text;
}
function settingsStatus(text,kind){state.settingsMessage={text,kind:kind||"info"};paintSettingsStatus();}
function paintSettingsDirty(){
  const badge=$("settingsDirtyBadge");if(badge)badge.hidden=!state.settingsDirty;
  const save=$("saveSettingsButton");if(save)save.classList.toggle("is-dirty",!!state.settingsDirty);
}
function markSettingsDirty(){state.settingsDirty=true;paintSettingsDirty();settingsStatus("Unsaved changes. Save to apply them to the running bot.","info");}
function money(value){return "₹"+Number(value||0).toLocaleString("en-IN");}
function accountRows(){
  const model=state.settings;if(!model)return "";
  return model.accounts.map((a,index)=>{
    const fixed=BUILTIN_ACCOUNTS.includes(a.name);
    // Every number carries a visible unit label: three bare boxes in a row gave
    // no way to tell capital from trade count from risk.
    const field=(key,label,min,max,step)=>`<label class="settings-field"><span class="settings-field-label">${escapeHtml(label)}</span><input class="settings-input" type="number" value="${a[key]}" min="${min}" max="${max}" step="${step}" inputmode="numeric" data-account-index="${index}" data-account-field="${key}"${fixed?" disabled":""} aria-label="${escapeHtml(a.name)} ${escapeHtml(label)}"></label>`;
    const remove=fixed?"":`<button class="chip-option settings-toggle" type="button" data-remove-account="${index}" aria-label="Remove ${escapeHtml(a.name)}">Remove</button>`;
    return`<div class="settings-row settings-account"><div class="settings-account-head"><span class="settings-label">${escapeHtml(a.name)}</span>${remove}</div>`
      +`<div class="settings-account-fields">${field("starting_balance","Capital",1,100000000,1000)}${field("daily_trade_limit","Trades / day",1,500,1)}${field("risk_per_trade","Risk / trade",100,500000,100)}</div>`
      +`<span class="settings-hint">${money(a.starting_balance)} · ${a.daily_trade_limit} trades · ${money(a.risk_per_trade)} risk · ${money(a.daily_trade_limit*a.risk_per_trade)}/day</span></div>`;
  }).join("");
}
function assetRows(){
  const model=state.settings;if(!model)return "";
  // "Assets" is already the group header directly above this row.
  if(!model.assets.length)return`<div class="settings-row"><span class="settings-label">Added assets</span><div class="settings-inline"><span class="settings-hint">None added. The 25 shipped assets are always traded.</span></div></div>`;
  return model.assets.map((asset,index)=>{
    const groups=`<select class="settings-input" data-asset-index="${index}" data-asset-field="group" aria-label="Asset group">${model.groups.map(x=>`<option value="${escapeHtml(x)}"${x===asset.group?" selected":""}>${escapeHtml(x)}</option>`).join("")}</select>`;
    const strategies=model.strategies.map(id=>`<button class="chip-option${asset.strategies.includes(id)?" active":""}" type="button" aria-pressed="${asset.strategies.includes(id)}" data-asset-index="${index}" data-asset-strategy="${escapeHtml(id)}">${escapeHtml(model.strategyNames[id]||id)}</button>`).join("");
    const text=(field,placeholder)=>`<input class="settings-input" type="text" value="${escapeHtml(asset[field])}" placeholder="${escapeHtml(placeholder)}" data-asset-index="${index}" data-asset-field="${field}" aria-label="${escapeHtml(placeholder)}">`;
    const tag=asset.symbol||"new asset";
    return`<div class="settings-row"><span class="settings-label">${escapeHtml(tag)}</span><div class="settings-inline">${text("label","Label")}${text("yahoo_symbol","Yahoo symbol")}${groups}<button class="chip-option settings-toggle" type="button" data-remove-asset="${index}" aria-label="Remove ${escapeHtml(tag)}">Remove</button></div></div>`
      +`<div class="settings-row"><span class="settings-label">${escapeHtml(tag)} scan</span><div class="settings-inline">${strategies}</div></div>`;
  }).join("");
}
function settingsChip(kind,index,value,label,active){
  return `<button class="chip-option${active?" active":""}" type="button" aria-pressed="${active?"true":"false"}" data-settings-kind="${kind}" data-settings-index="${index}" data-settings-value="${escapeHtml(value)}">${escapeHtml(label)}</button>`;
}
function ruleRows(){
  const model=state.settings;if(!model)return "";
  return model.rules.map((rule,index)=>{
    const account=escapeHtml(rule.account.toUpperCase());
    const strategies=model.strategies.map(id=>settingsChip("strategies",index,id,model.strategyNames[id]||id,(rule.strategies||model.strategies).includes(id))).join("");
    const assets=model.groups.map(g=>settingsChip("asset_groups",index,g,g,(rule.asset_groups||model.groups).includes(g))).join("");
    const windows=ROUTING_WINDOWS.map(([value,label])=>settingsChip("in_ny_session",index,value,label,String(rule.in_ny_session)===value)).join("");
    // Reorder buttons are not options: `settings-move` gives them their own
    // square icon geometry and a visible disabled state. They belong to the
    // rule they move, so they sit on the rule's own heading.
    const move=(delta,label,disabled)=>`<button class="chip-option settings-toggle settings-move" type="button" data-settings-move="${delta}" data-settings-index="${index}" aria-label="${escapeHtml(label)}"${disabled?" disabled":""}>${delta<0?"↑":"↓"}</button>`;
    const group=(caption,chips)=>`<div class="settings-rule-group"><span class="settings-field-label">${escapeHtml(caption)}</span><div class="settings-inline">${chips}</div></div>`;
    // One block per rule. It used to be three rows whose labels repeated the
    // account name, so a screen reader and the eye both read twelve chips with
    // no owner: strategies, asset groups and session window now belong to the
    // single heading above them.
    return`<div class="settings-row settings-rule"><div class="settings-rule-head"><span class="settings-label">${index+1} · ${account}</span><span class="settings-rule-move">${move(-1,"Move "+rule.account+" earlier",index===0)}${move(1,"Move "+rule.account+" later",index===model.rules.length-1)}</span></div>`
      +group("Strategies",strategies)+group("Assets",assets)+group("Session",windows)+`</div>`;
  }).join("");
}
function renderSettings(){
  const model=state.settings;if(!model)return;
  const accounts=$("settingsAccounts"),assets=$("settingsAssets"),rules=$("settingsRules");
  if(accounts)accounts.innerHTML=accountRows();
  if(assets)assets.innerHTML=assetRows();
  if(rules)rules.innerHTML=ruleRows();
  const hours=Array.from({length:24},(_,h)=>`<option value="${h}">${String(h).padStart(2,"0")}:00</option>`).join("");
  const start=$("settingsStartHour"),end=$("settingsEndHour"),live=$("settingsNow");
  if(start&&!start.options.length)start.innerHTML=hours;
  if(end&&!end.options.length)end.innerHTML=hours;
  if(!state.settingsDirty){if(start)start.value=String(model.session.start_hour);if(end)end.value=String(model.session.end_hour);}
  if(live)live.innerHTML=`<option>${model.session.active_now?"Inside session":"Outside session"}</option>`;
  const tag=$("settingsSessionTag");
  if(tag)tag.textContent=model.rules.length?`${String(model.session.start_hour).padStart(2,"0")}:00-${String(model.session.end_hour).padStart(2,"0")}:00 NY`:"No settings";
}
function settingsToggle(kind,index,value){
  const rule=state.settings?.rules[index];if(!rule)return;
  if(kind==="in_ny_session"){rule.in_ny_session=value==="null"?null:value==="true";}
  else{
    const every=kind==="strategies"?state.settings.strategies:state.settings.groups;
    const current=rule[kind]??[...every];
    const next=current.includes(value)?current.filter(v=>v!==value):[...current,value];
    if(!next.length){settingsStatus(rule.account.toUpperCase()+" must catch at least one "+(kind==="strategies"?"strategy":"asset group")+".","error");return;}
    rule[kind]=next.length===every.length?null:next;
  }
  markSettingsDirty();
}
function settingsMove(index,delta){
  const rules=state.settings?.rules,target=index+delta;
  if(!rules||target<0||target>=rules.length)return;
  const [moved]=rules.splice(index,1);rules.splice(target,0,moved);
  markSettingsDirty();
}
function nextAccountName(){
  const taken=new Set(state.settings.accounts.map(a=>a.name));
  let i=1;while(taken.has("book_"+i))i++;
  return "book_"+i;
}
function addAccount(){
  const model=state.settings;if(!model)return;
  const name=nextAccountName();
  model.accounts.push({name,starting_balance:100000,daily_trade_limit:5,risk_per_trade:2000});
  // A new account needs a routing rule in the same save or it is unreachable
  // and the server refuses the whole document. Seeded at the end on one
  // strategy and one group; the operator narrows or widens it from there.
  model.rules.push({account:name,strategies:[model.strategies[0]].filter(Boolean),asset_groups:[model.groups[0]].filter(Boolean),in_ny_session:null});
  markSettingsDirty();renderSettings();
}
function addAsset(){
  const model=state.settings;if(!model)return;
  model.assets.push({symbol:"",label:"",yahoo_symbol:"",market:"",asset_type:"",group:model.groups[0]||"",currency:"INR",sweep_timeframe:"4H",strategies:[]});
  markSettingsDirty();renderSettings();
}
function settingsPayload(){
  const model=state.settings,start=$("settingsStartHour"),end=$("settingsEndHour");
  return{settings:{
    accounts:model.accounts.map(a=>({name:a.name,starting_balance:a.starting_balance,daily_trade_limit:a.daily_trade_limit,risk_per_trade:a.risk_per_trade})),
    assets:model.assets.map(a=>({symbol:a.symbol,label:a.label,yahoo_symbol:a.yahoo_symbol,market:a.market,asset_type:a.asset_type,group:a.group,currency:a.currency,strategies:a.strategies})),
    session:{start_hour:Number(start?.value||0),end_hour:Number(end?.value||0)},
    rules:model.rules.map(r=>({account:r.account,strategies:r.strategies,asset_groups:r.asset_groups,in_ny_session:r.in_ny_session}))}};
}
async function postSettings(body,button){
  const model=state.settings;if(!model)return;
  button.disabled=true;settingsStatus("Saving to the server…","loading");
  try{
    const response=await fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body),cache:"no-store"});
    const result=await readJsonResponse(response,"Settings API");
    if(result.ok===false)throw new Error(result.error||"Settings change failed");
    state.settingsDirty=false;
    paintSettingsDirty();
    if(result.settings){const fresh=settingsModel(result.settings);model.accounts=fresh.accounts;model.assets=fresh.assets;model.rules=fresh.rules;model.session=fresh.session;}
    renderSettings();
    // The refresh runs first: loadDashboard() re-renders Tools and would
    // otherwise overwrite the green confirmation with its neutral status line.
    await loadDashboard();
    settingsStatus(result.message||"Settings saved.","success");
  }catch(error){
    // The running configuration is untouched when a save is refused, so keep
    // the edits on screen for the operator to correct.
    settingsStatus(error.message,"error");
  }finally{button.disabled=false;}
}
function saveSettings(){const button=$("saveSettingsButton");if(button)postSettings(settingsPayload(),button);}
function resetSettings(){const button=$("resetSettingsButton");if(button)postSettings({settings:{action:"reset"}},button);}
function bootstrapDashboard(){try{initAppearance();bindEvents();syncAllToolCollapseControls();const marketClock=$("marketClock");if(marketClock){marketClock.textContent=clock();setInterval(()=>{const clockEl=$("marketClock");if(clockEl)clockEl.textContent=clock();},1000);}loadDashboard();setInterval(loadDashboard,CONFIG.refreshMs);}catch(error){console.error("Dashboard bootstrap failed",error);showConnectionStatus(false,"Dashboard startup problem. Check browser console.");}}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",bootstrapDashboard,{once:true});else bootstrapDashboard();

function closeTradeDrawer(){const drawer=document.getElementById("tradeDetailDrawer");if(!drawer)return;drawer.classList.remove("open");drawer.setAttribute("aria-hidden","true");document.body.classList.remove("drawer-open");if(lastTradeDrawerFocus&&lastTradeDrawerFocus.isConnected)lastTradeDrawerFocus.focus();lastTradeDrawerFocus=null;}
let lastTradeDrawerFocus=null;
function openTradeDetail(trade){const plan=trade.plan||trade,status=String(trade.status||"OPEN").toUpperCase(),side=String(plan.side||trade.type||"").toUpperCase(),symbol=trade.symbol||plan.symbol||"Paper trade",label=assetLabel(symbol,trade.label||plan.label),strategy=strategyLabel(plan.strategy||trade.strategy),pnl=trade.pnl;let drawer=document.getElementById("tradeDetailDrawer");if(!drawer){drawer=document.createElement("div");drawer.id="tradeDetailDrawer";drawer.className="trade-drawer-shell";document.body.appendChild(drawer);}drawer.onclick=event=>{if(event.target===drawer||event.target.closest("[data-close-trade-detail]"))closeTradeDrawer();};drawer.setAttribute("aria-hidden","false");drawer.innerHTML=`<aside class="trade-drawer" role="dialog" aria-modal="true" aria-label="Trade details: ${escapeHtml(label)}"><button class="drawer-close" type="button" data-close-trade-detail aria-label="Close trade details">×</button><span class="eyebrow">TRADE DETAIL</span><h2>${escapeHtml(label)}</h2><div class="drawer-status"><span class="trade-status ${status.toLowerCase()}">${status}</span><b>${escapeHtml(side||"—")}</b></div><div class="drawer-price-grid"><div><span>Entry</span><b>${price(plan.entry??trade.entry)}</b></div><div><span>Current / Exit</span><b>${status==="CLOSED"?price(trade.exit_price):price(trade.current_price??trade.last_price)}</b></div><div><span>Stop loss</span><b>${price(plan.stop_loss??trade.sl)}</b></div><div><span>Take profit</span><b>${price(plan.take_profit??trade.tp)}</b></div></div><section><h3>Signal details</h3><div class="drawer-details"><div><span>Strategy</span><b>${escapeHtml(strategy)}</b></div><div><span>Account</span><b>${escapeHtml(String(trade.account||"nifty").toUpperCase())}</b></div><div><span>Quantity</span><b>${number(plan.quantity??trade.qty,4)}</b></div><div><span>Planned risk</span><b>${inr(plan.planned_risk??trade.planned_risk)}</b></div><div><span>Signal created</span><b>${escapeHtml(timestamp(plan.signal_timestamp||trade.signal_ts||trade.created_at))}</b></div>${status==="CLOSED"?`<div><span>P/L</span><b class="${Number(pnl)>=0?"positive":"negative"}">${inr(pnl)}</b></div><div><span>Closed</span><b>${escapeHtml(timestamp(trade.closed_at||trade.exit_timestamp))}</b></div><div><span>Exit reason</span><b>${escapeHtml(trade.exit_reason||trade.result||"—")}</b></div>`:""}</div></section></aside>`;lastTradeDrawerFocus=document.activeElement instanceof HTMLElement?document.activeElement:null;document.body.classList.add("drawer-open");requestAnimationFrame(()=>{drawer.classList.add("open");const closeButton=drawer.querySelector(".drawer-close");if(closeButton)closeButton.focus();});}
