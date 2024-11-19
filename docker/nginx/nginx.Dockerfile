FROM nginx

COPY mlaps.conf /etc/nginx/conf.d/mlaps.conf
COPY htaccess.htpasswd /shared/htaccess.htpasswd

CMD ["nginx", "-g", "daemon off;"]
