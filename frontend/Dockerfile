# ==============================================================================
# DOCKERFILE — Frontend Next.js 16 (Standalone Production Build)
# ==============================================================================
# Multi-stage build siguiendo las recomendaciones oficiales de Next.js:
#   1. deps: instala node_modules
#   2. builder: genera el bundle standalone optimizado
#   3. runner: imagen mínima con solo el bundle de producción
# ==============================================================================

# ---- Stage 1: Dependencies ----
FROM node:22-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# ---- Stage 2: Builder ----
FROM node:22-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Definir la URL del backend para build-time (client-side)
# En Docker, el navegador accede al backend por el puerto expuesto en el host
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# ---- Stage 3: Runner ----
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

# Crear usuario no-root para seguridad
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copiar archivos estáticos y el bundle standalone
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
