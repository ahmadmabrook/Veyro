/**
 * Next configuration. Deliberately small: the design system is CSS custom properties and the
 * foundation modules are plain ESM, so there is no build-time token pipeline to configure.
 *
 * `VEYRO_API_ORIGIN` is where the FastAPI backend answers. It is read at request time rather
 * than inlined into the client bundle, because the browser must never hold a tenant's API
 * origin as a build constant -- the same deployment serves every tenant.
 */
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // The browser never calls the backend directly: every request goes through this app's own
  // server actions, so the session cookie stays httpOnly and the bearer token never reaches
  // client JavaScript. See src/lib/api.ts.
  //
  // **`127.0.0.1` has to be here or the dev server silently serves an un-hydrated page.**
  // Next 16 blocks cross-origin requests to its own dev resources, and `localhost` and
  // `127.0.0.1` are different origins to a browser -- so visiting the second one got the HTML
  // and the chunks and then a 403 on the HMR socket, and the React tree never attached. The
  // page looked right and no handler ran. That matters beyond developer convenience: a
  // Playwright run against `127.0.0.1` would have driven a dead page and, for every assertion
  // about server-rendered text, reported green.
  allowedDevOrigins: ["127.0.0.1"],
  experimental: {},
};

export default nextConfig;
