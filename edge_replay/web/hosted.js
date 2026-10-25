/* Hosting adapter: the server computes; this tab holds temporary work; cloud saves are durable. */
(() => {
  'use strict';
  const KIND = 'EdgeReplay', nativeFetch = globalThis.fetch.bind(globalThis);
  const key = `hosted:${KIND}:v1`;
  let state = {datasets: [], runs: [], recordings: [], investigations: [], csv: {}}, catalog = null, refreshed = false, warning = '';
  const obj = value => value && typeof value === 'object' && !Array.isArray(value);
  function valid(value) {
    if (!obj(value) || !['datasets','runs','recordings','investigations'].every(k => Array.isArray(value[k])) || !obj(value.csv)) return false;
    if (!value.datasets.every(d => obj(d) && typeof d.id === 'string' && typeof d.name === 'string' && Array.isArray(d.documents) && Array.isArray(d.queries))) return false;
    if (!value.runs.every(r => obj(r) && typeof r.id === 'string' && obj(r.dataset) && obj(r.results) && obj(r.results.methods))) return false;
    if (!value.recordings.every(r => obj(r) && typeof r.id === 'string' && typeof r.name === 'string' && ['signals','can'].includes(r.mode) && Array.isArray(r.channels) && Array.isArray(r.rows))) return false;
    return value.investigations.every(r => obj(r) && typeof r.id === 'string' && obj(r.spec) && Array.isArray(r.spec.bounds) && obj(r.sources) && ['before','after'].every(k => obj(r.sources[k]) && typeof r.sources[k].url === 'string'));
  }
  try {
    const stored = sessionStorage.getItem(key);
    if (stored) { const parsed = JSON.parse(stored); if (!valid(parsed)) throw Error('invalid session'); state = parsed; }
  } catch (_) {
    warning = 'A previous browser session could not be restored. Import your export or open a cloud copy.';
    try { sessionStorage.removeItem(key); } catch (_) { /* Storage is optional. */ }
  }
  function banner() {
    const node = document.getElementById('hosted-storage-notice');
    if (node) node.textContent = warning || 'Hosted workspace · Work is temporary in this browser tab. Use Cloud → Save a new copy, or export a file, to keep it.';
  }
  function persist() {
    try { sessionStorage.setItem(key, JSON.stringify(state)); }
    catch (_) { warning = 'Browser storage is full or blocked. Work is in memory only. Save a cloud copy or export before leaving this page.'; }
    banner();
  }
  function response(value, status = 200) { return new Response(JSON.stringify(value), {status, headers: {'Content-Type': 'application/json'}}); }
  function missing(label) { return response({error: `${label} is not available in this browser session. Open a cloud copy or import it again.`}, 404); }
  function cache(collection, value) {
    state[collection] = [value, ...state[collection].filter(row => row.id !== value.id)]; persist();
  }
  function report(record) {
    const s=record.spec;
    return [`# ${s.name}`, '', `Created: ${record.created}`, `Layer: ${s.layer}`, `Bounds (west, south, east, north): ${s.bounds.join(', ')}`, 'CRS: EPSG:4326; WMS 1.1.1 longitude/latitude ordering.', `Metadata verified: ${record.catalog_verified}`, '', '## Observation notes', '', s.notes || 'No observations recorded.', '', '## Source provenance', '', ...['before','after'].flatMap(label => {const source=record.sources[label];return [`### ${label} · ${s[label]}`, `URL: ${source.url}`, `SHA256: ${source.sha256}`, `Fetched: ${source.fetched_at}`, `Bytes: ${source.bytes}`, ''];}), '## Interpretation limits', '', 'NASA GIBS browse imagery is for visual inspection. Clouds, haze, season, viewing geometry and processing can change appearance. No quantitative vegetation, burn severity, land-loss or causal analysis is computed.', '', 'Imagery: NASA EOSDIS GIBS. https://nasa-gibs.github.io/gibs-api-docs/access-basics/', ''].join('\n');
  }
  async function adapter(input, options = {}) {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(raw, location.origin), method = (options.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) return nativeFetch(input, options);
    const path = url.pathname;
    if (method === 'GET') {
      if (KIND === 'RetrievalLab' && path === '/api/state') return response({datasets:state.datasets,runs:state.runs.map(r=>({id:r.id,created:r.created,name:r.dataset.name,k:r.results.k})),version:'hosted'});
      if (KIND === 'RetrievalLab' && path.startsWith('/api/runs/')) { const run=state.runs.find(r=>r.id===decodeURIComponent(path.slice(10))); return run ? response(run) : missing('Run'); }
      if (KIND === 'EdgeReplay' && path === '/api/recordings') return response({recordings:state.recordings.map(r=>({id:r.id,created:r.created,name:r.name,mode:r.mode,duration_ms:r.duration_ms,sha256:r.sha256})),version:'hosted'});
      if (KIND === 'EdgeReplay' && path.startsWith('/api/recordings/')) {
        const id=decodeURIComponent(path.slice(16)), record=state.recordings.find(r=>r.id===id);
        if (!record) return missing('Recording');
        if (url.searchParams.get('format') === 'csv') {
          const csv=state.csv[id]; if (typeof csv !== 'string') return response({error:'Original CSV is unavailable. Export JSON or reimport the original recording.'},404);
          return new Response(csv, {headers:{'Content-Type':'text/csv; charset=utf-8'}});
        }
        return response(record);
      }
      if (KIND === 'GeoTrace' && path === '/api/state') {
        if (!catalog) { const result=await nativeFetch(input,options);if(!result.ok)return result;catalog=(await result.json()).catalog; }
        return response({catalog,investigations:state.investigations,version:'hosted'});
      }
      if (KIND === 'GeoTrace' && path.startsWith('/api/export/')) {
        const id=decodeURIComponent(path.slice(12)),record=state.investigations.find(r=>r.id===id);
        if (!record) return missing('Investigation');
        return url.searchParams.get('format')==='md' ? new Response(report(record),{headers:{'Content-Type':'text/markdown; charset=utf-8'}}) : response(record);
      }
    }
    let data;
    if (method === 'POST' && typeof options.body === 'string') {
      try { data=JSON.parse(options.body); } catch (_) { return response({error:'Request must be valid JSON.'},400); }
      if (KIND === 'RetrievalLab' && path === '/api/runs') {
        const dataset=state.datasets.find(d=>d.id===data.dataset_id);
        if (!dataset) return missing('Dataset');
        data={...data,dataset}; options={...options,body:JSON.stringify(data)};
      }
      if (KIND === 'GeoTrace' && refreshed && ['/api/compare','/api/investigations'].includes(path)) options={...options,body:JSON.stringify({...data,_refresh_catalog:true})};
    }
    const result = await nativeFetch(input,options);
    if (result.ok && method === 'POST') {
      const value=await result.clone().json();
      if (KIND === 'RetrievalLab' && path === '/api/datasets') cache('datasets',value);
      if (KIND === 'RetrievalLab' && path === '/api/runs') cache('runs',value);
      if (KIND === 'EdgeReplay' && path === '/api/recordings') { state.csv[value.id]=data.csv;cache('recordings',value); }
      if (KIND === 'GeoTrace' && path === '/api/investigations') cache('investigations',value);
      if (KIND === 'GeoTrace' && path === '/api/catalog/refresh') { catalog=value;refreshed=true; }
    }
    return result;
  }
  globalThis.fetch=adapter;
  globalThis.HostedWorkspace={hosted:true,imageSource:source=>source.url};
  document.addEventListener('DOMContentLoaded',()=>{
    const notice=document.createElement('p');notice.id='hosted-storage-notice';notice.className='hosted-storage-notice';notice.setAttribute('role','status');
    document.body.prepend(notice);banner();
  });
  // Download links created by existing app code still export this session's actual data.
  document.addEventListener('click',async event=>{
    const link=event.target.closest?.('a[download]');if(!link)return;
    const url=new URL(link.href,location.origin);
    if(url.origin!==location.origin || !/^\/api\/(runs|recordings|export)\//.test(url.pathname))return;
    event.preventDefault();
    try {
      const result=await adapter(url.href);if(!result.ok)throw Error((await result.json()).error);
      const blob=await result.blob(), href=URL.createObjectURL(blob), anchor=document.createElement('a');anchor.href=href;
      const extension=url.searchParams.get('format')==='csv'?'csv':url.searchParams.get('format')==='md'?'md':'json';
      anchor.download=`${KIND.toLowerCase()}-${url.pathname.split('/').at(-1)}.${extension}`;document.body.append(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(href),1000);
    } catch(error){warning=error.message;banner();}
  },true);
})();
