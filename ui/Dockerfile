FROM nginx:alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY index.html /usr/share/nginx/html/index.html
COPY static /usr/share/nginx/html/static
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
