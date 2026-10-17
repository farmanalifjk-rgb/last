// Load browser ES modules from src/ in Node through Vite's SSR loader, so the
// same extensionless imports and import.meta.env that Vite builds are honoured.
import { createServer } from "vite";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

export async function withSrcLoader(fn) {
    const server = await createServer({
        root,
        configFile: false,
        logLevel: "error",
        appType: "custom",
        server: { middlewareMode: true, hmr: false, watch: null },
        optimizeDeps: { noDiscovery: true, include: [] },
    });
    try {
        return await fn((path) => server.ssrLoadModule(path));
    } finally {
        await server.close();
    }
}
