/**
 * Lookup for the generated operations map (operations.json, built by
 * frontend/scripts/map-api.py from the backend OpenAPI schema).
 *
 * Every API call a page makes goes through getOp(), so a call to an operation
 * the map does not know fails loudly during development instead of quietly
 * calling a wrong URL.
 */
import OPERATIONS from "./operations.json";
import { apiJson, apiList, buildQuery } from "../../services/api.js";

export function findOp(method, path) {
    return OPERATIONS[`${method} ${path}`] || null;
}

export function getOp(method, path) {
    const op = findOp(method, path);
    if (!op) throw new Error(`Operation is not in the API map: ${method} ${path}`);
    return op;
}

/** Replace {name} placeholders in a schema path with values. */
export function fillPath(template, values = {}) {
    return template.replace(/\{(\w+)\}/g, (_, key) => {
        const value = values[key];
        if (value === undefined || value === null || value === "") {
            throw new Error(`Missing value for ${key}.`);
        }
        return encodeURIComponent(String(value));
    });
}

export function withQuery(path, params = {}) {
    return `${path}${buildQuery(params)}`;
}

/** Call an operation. Returns parsed JSON. */
export function callOp(method, template, { values, query, body } = {}) {
    getOp(method, template);
    const path = withQuery(fillPath(template, values), query);
    const options = { method };
    if (body !== undefined) options.body = JSON.stringify(body);
    return apiJson(path, options);
}

/** Call a list operation and return the normalised { results, count, ... } shape. */
export function listOp(template, query = {}) {
    getOp("GET", template);
    return apiList(withQuery(template, query));
}
