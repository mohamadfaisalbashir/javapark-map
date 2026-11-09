FROM node:22-alpine
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Tujuan proksi /api/* (next.config.js), dilihat dari container web di jaringan Compose.
ENV API_INTERNAL_URL=http://api:8000
# NEXT_PUBLIC_* disematkan ke bundel saat build (dipanggil dari browser).
# FR-06: kunci Maps Embed API (kosong = tombol 360° Street View disembunyikan). Lihat .env.example.
ARG NEXT_PUBLIC_GOOGLE_MAPS_EMBED_KEY=
ENV NEXT_PUBLIC_GOOGLE_MAPS_EMBED_KEY=$NEXT_PUBLIC_GOOGLE_MAPS_EMBED_KEY
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
