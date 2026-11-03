FROM node:22-alpine
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# NEXT_PUBLIC_* disematkan ke bundel saat build (dipanggil dari browser).
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
# FR-06: kunci Maps Embed API (kosong = tombol 360° Street View disembunyikan). Lihat .env.example.
ARG NEXT_PUBLIC_GOOGLE_MAPS_EMBED_KEY=
ENV NEXT_PUBLIC_GOOGLE_MAPS_EMBED_KEY=$NEXT_PUBLIC_GOOGLE_MAPS_EMBED_KEY
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
