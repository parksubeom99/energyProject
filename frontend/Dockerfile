# GreenPulse 프론트엔드 — Node.js + Vite + React
# 빌드: docker build -t gp-frontend ./frontend
# 실행: docker run -p 5173:5173 gp-frontend

FROM node:22-alpine AS build

WORKDIR /app

# 의존성 먼저 설치 — Docker 레이어 캐싱
COPY package.json ./
RUN npm install --silent

# 소스 복사 + 빌드
COPY . .
RUN npm run build

# 프로덕션: nginx로 정적 파일 서빙
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
