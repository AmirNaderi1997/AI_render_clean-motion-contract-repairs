import { AsyncLocalStorage } from 'node:async_hooks';
const context = new AsyncLocalStorage();
const minimum = {image:150000,audio:200000,video:300000};
export function editorMediaPolicy(req,next) {
    if (req.headers['x-editorgpt-media-single-attempt'] !== '1') return next();
    const value = Number(req.headers['x-editorgpt-media-timeout-ms']);
    const timeout = Number.isFinite(value) ? Math.min(3600000,Math.max(0,value)) : 0;
    return context.run({timeout},next);
}
export function editorMediaTimeout(modality,original) {
    const policy=context.getStore();
    return policy ? Math.max(original,minimum[modality] || 200000,policy.timeout) : original;
}
export function editorMediaChain(rows) {
    return context.getStore() ? rows.slice(0,1) : rows;
}
