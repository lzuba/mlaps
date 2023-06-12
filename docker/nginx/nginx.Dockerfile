FROM nginx

COPY mlaps.conf /etc/nginx/conf.d/mlaps.conf

CMD ["nginx", "-g", "daemon off;"]
