# The frontend image is also the workspace's gateway: it serves the built SPA
# and routes /api/<service>/v1/* to whichever backend owns that namespace. One
# origin for the browser means no CORS anywhere and one place to set upload
# limits and timeouts.

FROM node:22-bookworm-slim AS builder

# pnpm, because pnpm-lock.yaml is the lockfile this repo actually has. Enabled
# through corepack so the version is pinned by the image rather than by whatever
# the build machine happens to have installed.
RUN corepack enable && corepack prepare pnpm@9 --activate

WORKDIR /build

# Dependencies first: this layer is cached unless the manifests change, which
# is what keeps a rebuild after a one-line UI fix down to seconds.
COPY package.json pnpm-lock.yaml ./
# --frozen-lockfile: a build that silently resolves different versions than the
# lockfile is not reproducible, and this image ships to an air-gapped network
# where "rebuild and see" is not available.
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm run build


FROM nginx:1.27-alpine

# The default site would otherwise shadow ours.
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx/workspace.conf /etc/nginx/conf.d/workspace.conf
COPY --from=builder /build/dist /usr/share/nginx/html

# workspace.conf includes this directory; nginx fails to start if an include
# path does not exist. Compose mounts the real tool configs over it, and an
# empty directory is what "no other tools deployed yet" looks like.
RUN mkdir -p /etc/nginx/workspace-modules

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/healthz || exit 1
